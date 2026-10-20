package no.bergenkommune.masterdb.service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import javax.sql.DataSource;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import no.bergenkommune.masterdb.domain.EtlJobStatus;

/**
 * Kjører "python3 etl/last_inn.py alle" og anvender den genererte SQL-en
 * direkte mot masterdb - automatisert versjon av det som til nå har vært en
 * manuell to-stegs prosess (generer SQL, se over den, kjør den selv).
 *
 * Trygt å automatisere fordi hver kommunes SQL allerede er pakket i sin egen
 * transaksjon (BEGIN/COMMIT) i last_inn.py, aldri overskriver manuelt satte
 * verdier, og en enkelt dårlig post/kommune aldri stopper resten av kjøringen
 * (se etl/README.md).
 *
 * Kjøringer serialiseres via en enkelt-tråds kø: to kjøringer skal aldri
 * overlappe, selv om flere mapping-endringer trigges tett i tid.
 */
@Service
public class EtlTriggerService {

    private static final Logger log = LoggerFactory.getLogger(EtlTriggerService.class);
    private static final int MAX_HISTORY = 20;
    private static final int LOG_TAIL_CHARS = 4000;

    private final Path workdir;
    private final String pythonBin;
    private final DataSource dataSource;
    private final ExecutorService executor = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "etl-trigger");
        t.setDaemon(true);
        return t;
    });

    private final Deque<EtlJobStatus> history = new ArrayDeque<>();
    private volatile EtlJobStatus latest;

    public EtlTriggerService(
        @Value("${etl.workdir}") String workdir,
        @Value("${etl.python-bin}") String pythonBin,
        DataSource dataSource
    ) {
        this.workdir = Path.of(workdir).toAbsolutePath().normalize();
        this.pythonBin = pythonBin;
        this.dataSource = dataSource;
    }

    public EtlJobStatus trigger(String triggeredBy) {
        EtlJobStatus job = new EtlJobStatus(triggeredBy);
        recordHistory(job);
        executor.submit(() -> runNow(job));
        return job;
    }

    public EtlJobStatus latest() {
        return latest;
    }

    public List<EtlJobStatus> history() {
        synchronized (history) {
            return List.copyOf(history);
        }
    }

    private void recordHistory(EtlJobStatus job) {
        synchronized (history) {
            history.addFirst(job);
            while (history.size() > MAX_HISTORY) {
                history.removeLast();
            }
        }
        latest = job;
    }

    private void runNow(EtlJobStatus job) {
        log.info("Starter last_inn.py alle (trigget av: {})", job.getTriggeredBy());
        try {
            ProcessBuilder pb = new ProcessBuilder(pythonBin, "etl/last_inn.py", "alle");
            pb.directory(workdir.toFile());
            Process process = pb.start();

            String sql = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            String stderr = new String(process.getErrorStream().readAllBytes(), StandardCharsets.UTF_8);
            int exitCode = process.waitFor();

            // Kode 2 = noen kommuner feilet å hente (loggført i synk_avvik),
            // men SQL-en for de som lyktes er fortsatt gyldig og skal
            // anvendes - se main() i etl/last_inn.py.
            if (exitCode != 0 && exitCode != 2) {
                job.markFailed("last_inn.py avsluttet med kode " + exitCode + ":\n" + tail(stderr));
                log.warn("ETL-kjøring feilet (kode {}): {}", exitCode, tail(stderr));
                return;
            }
            if (sql.isBlank()) {
                job.markFailed("Ingen SQL generert (tom stdout). Logg:\n" + tail(stderr));
                return;
            }

            try (Connection conn = dataSource.getConnection(); Statement stmt = conn.createStatement()) {
                stmt.execute(sql);
            }

            String melding = exitCode == 2
                ? "Fullført med advarsler - noen kommuner feilet å hente (se synk_avvik):\n" + tail(stderr)
                : "Fullført.";
            job.markSuccess(melding);
            log.info("ETL-kjøring fullført (trigget av: {})", job.getTriggeredBy());
        } catch (IOException | InterruptedException | SQLException e) {
            job.markFailed("Uventet feil: " + e);
            log.error("ETL-kjøring feilet uventet", e);
            if (e instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private static String tail(String text) {
        if (text.length() <= LOG_TAIL_CHARS) {
            return text;
        }
        return "..." + text.substring(text.length() - LOG_TAIL_CHARS);
    }
}
