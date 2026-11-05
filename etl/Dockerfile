FROM python:3.13-slim

# The proxy is needed both while building (apt) and at run time (fetching from
# Aktiv kommune and Matrikkel) on networks that require it. Empty values are
# ignored.
ARG http_proxy
ARG https_proxy
ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# psql is how the generated SQL reaches the database; tzdata makes TZ (the time
# of the nightly sync) work; ca-certificates provides update-ca-certificates
# for the optional extra CA in ./certs (see run.sh).
RUN apt-get update \
	&& apt-get install -y --no-install-recommends ca-certificates postgresql-client tzdata \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN chmod +x /app/run.sh

ENTRYPOINT ["/app/run.sh"]
CMD ["daemon"]
