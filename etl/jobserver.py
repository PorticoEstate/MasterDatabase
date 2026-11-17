"""Job queue, nightly timer and internal HTTP API of the etl container.

etl.py daemon wires this up. The module knows nothing about what the jobs do:
it gets a dict of runners {job type: function(args) -> bool} from etl.py.

All jobs write the same tables, so a single worker thread runs them one at a
time, in the order they were queued. The HTTP API only enqueues and reports;
it never blocks on a job.

THE API HAS NO AUTHENTICATION, by decision. Its only protection is that the etl
service has no `ports:` mapping in docker-compose.yml, so only containers on
the compose network (in practice the backend) can reach it. Never publish the
port. Because of that, input validation here is strict.
"""

import collections
import datetime
import json
import queue
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Job types that can be started over HTTP. build, prune and the internal
# startup / nightly-load jobs are not exposed.
HTTP_TYPES = ("sync", "geocode", "gater")

KOMMUNENR = re.compile(r"[0-9]{4}")
MAX_KOMMUNENR = 500
MAX_BODY = 64 * 1024
MAX_JOBS = 50
MAX_OUTPUT_LINES = 200


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


class Job:
    def __init__(self, job_type, args):
        self.id = str(uuid.uuid4())
        self.type = job_type
        self.args = args
        self.status = "queued"
        self.queued_at = now_iso()
        self.started_at = None
        self.finished_at = None
        self.message = None
        self.output = collections.deque(maxlen=MAX_OUTPUT_LINES)

    def key(self):
        return (self.type, tuple(self.args))

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "args": list(self.args),
            "status": self.status,
            "queuedAt": self.queued_at,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "message": self.message,
            "output": list(self.output),
        }


class JobServer:
    def __init__(self, runners, set_log_sink, log):
        self.runners = runners
        self.set_log_sink = set_log_sink
        self.log = log
        self.lock = threading.Lock()
        self.jobs = collections.OrderedDict()  # id -> Job, oldest first
        self.pending = queue.Queue()
        self.running = None

    # --- queue ---------------------------------------------------------

    def submit(self, job_type, args=()):
        """Queues a job. Returns (job, deduplicated, queue_position). An identical
        job (same type and arguments) that is still waiting is returned instead of
        adding another. queue_position counts the jobs ahead of it, including the
        one that is running."""
        args = tuple(sorted(set(args)))
        with self.lock:
            waiting = [j for j in self.jobs.values() if j.status == "queued"]
            for j in waiting:
                if j.key() == (job_type, args):
                    return j, True, self._position(j, waiting)
            job = Job(job_type, args)
            self.jobs[job.id] = job
            self._trim()
            self.pending.put(job)
            self.log("job %s queued: %s %s" % (job.id[:8], job.type, " ".join(job.args)))
            return job, False, self._position(job, waiting + [job])

    def _position(self, job, waiting):
        ahead = waiting.index(job)
        if self.running is not None:
            ahead += 1
        return ahead

    def _trim(self):
        """Keeps the last MAX_JOBS jobs; queued and running ones are never dropped."""
        for job_id in list(self.jobs):
            if len(self.jobs) <= MAX_JOBS:
                break
            if self.jobs[job_id].status in ("ok", "failed"):
                del self.jobs[job_id]

    def get(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            return job.to_dict() if job else None

    def recent(self):
        with self.lock:
            return [j.to_dict() for j in reversed(self.jobs.values())]

    # --- worker --------------------------------------------------------

    def start_worker(self):
        threading.Thread(target=self._work, name="etl-worker", daemon=True).start()

    def _work(self):
        while True:
            job = self.pending.get()
            with self.lock:
                job.status = "running"
                job.started_at = now_iso()
                self.running = job
            self.log("job %s running: %s" % (job.id[:8], job.type))
            self.set_log_sink(job.output.append)
            try:
                ok = self.runners[job.type](list(job.args))
                message = "completed" if ok else "failed, see output"
            except Exception as exc:  # a crashing job must not kill the worker
                ok = False
                message = "crashed: %s" % exc
                job.output.append(message)
            self.set_log_sink(None)
            with self.lock:
                job.status = "ok" if ok else "failed"
                job.message = message
                job.finished_at = now_iso()
                self.running = None
            self.log("job %s finished: %s (%s)" % (job.id[:8], job.status, job.type))

    # --- nightly timer -------------------------------------------------

    def start_nightly(self, seconds_until_sync, synk_tid):
        threading.Thread(target=self._nightly, args=(seconds_until_sync, synk_tid),
                         name="etl-nightly", daemon=True).start()

    def _nightly(self, seconds_until_sync, synk_tid):
        """At SYNK_TID: sync (or the build, if the vocabulary is still empty), then
        geocode, then prune. Geocode runs even if the sync failed. gater is not
        part of the nightly cycle."""
        while True:
            venting = seconds_until_sync()
            self.log("next sync at %s (in %ds)" % (synk_tid, venting))
            time.sleep(venting)
            for job_type in ("nightly-load", "geocode", "prune"):
                self.submit(job_type)
            time.sleep(60)  # never fire twice for the same minute

    # --- HTTP ----------------------------------------------------------

    def make_http_server(self, port):
        jobserver = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *args):
                pass  # job lifecycle is logged by JobServer; /health would be noise

            def reply(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def error(self, status, message):
                self.reply(status, {"error": message})

            def do_GET(self):
                path = self.path.split("?", 1)[0]
                if path == "/health":
                    self.reply(200, {"status": "UP"})
                elif path == "/jobs":
                    self.reply(200, jobserver.recent())
                elif path.startswith("/jobs/") and "/" not in path[len("/jobs/"):]:
                    job = jobserver.get(path[len("/jobs/"):])
                    if job is None:
                        self.error(404, "unknown job")
                    else:
                        self.reply(200, job)
                else:
                    self.error(404, "not found")

            def do_POST(self):
                path = self.path.split("?", 1)[0]
                if path in ("/health", "/jobs"):
                    return self.error(405, "method not allowed")
                if not path.startswith("/jobs/") or "/" in path[len("/jobs/"):]:
                    return self.error(404, "not found")
                job_type = path[len("/jobs/"):]
                if job_type not in HTTP_TYPES:
                    return self.error(404, "unknown job type")
                try:
                    args = self.read_args(job_type)
                except ValueError as exc:
                    return self.error(400, str(exc))
                except OverflowError:
                    return self.error(413, "request body too large")
                except LookupError:
                    return self.error(411, "Content-Length required (chunked bodies are not supported)")
                job, dedup, position = jobserver.submit(job_type, args)
                self.reply(202, {"id": job.id, "type": job.type, "status": job.status,
                                 "queuePosition": position, "deduplicated": dedup})

            def do_PUT(self):
                self.error(405, "method not allowed")

            do_DELETE = do_PATCH = do_PUT

            def read_args(self, job_type):
                """Returns the validated argument list. The body is optional; if
                present it must be a JSON object, and only gater takes a key
                (kommunenr: a list of four-digit strings)."""
                if self.headers.get("Transfer-Encoding") and self.headers.get("Content-Length") is None:
                    # Would otherwise be read as an empty body, and a gater job for one
                    # kommune would silently become a job for all of them.
                    raise LookupError
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    raise ValueError("invalid Content-Length")
                if length < 0:
                    raise ValueError("invalid Content-Length")
                if length > MAX_BODY:
                    raise OverflowError
                raw = self.rfile.read(length) if length else b""
                if not raw.strip():
                    return []
                try:
                    body = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    raise ValueError("body must be JSON")
                if not isinstance(body, dict):
                    raise ValueError("body must be a JSON object")
                allowed = {"kommunenr"} if job_type == "gater" else set()
                unknown = set(body) - allowed
                if unknown:
                    raise ValueError("unknown field(s) for %s: %s" % (job_type, ", ".join(sorted(map(str, unknown)))))
                nrs = body.get("kommunenr")
                if nrs is None:
                    return []
                if not isinstance(nrs, list) or not nrs:
                    raise ValueError("kommunenr must be a non-empty list")
                if len(nrs) > MAX_KOMMUNENR:
                    raise ValueError("at most %d kommunenr per request" % MAX_KOMMUNENR)
                for nr in nrs:
                    if not isinstance(nr, str) or not KOMMUNENR.fullmatch(nr):
                        raise ValueError("kommunenr must be four digits")
                return nrs

        return ThreadingHTTPServer(("0.0.0.0", port), Handler)
