package no.bergenkommune.masterdb.service;

import java.io.IOException;
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import no.bergenkommune.masterdb.domain.MappingFile;

/**
 * Overvåker de tre mapping.json-filene på disk og trigger en ny
 * last_inn.py-kjøring når en av dem endres - uansett om endringen kom fra
 * admin-API-et (MappingFileService) eller fra en vanlig fil-redigering/git-
 * endring i containerens mount av repoet.
 *
 * Flere raske endringer (f.eks. en editor som lagrer i flere skritt) slås
 * sammen til én kjøring via en debounce-timer (etl.debounce-seconds).
 */
@Service
public class MappingFileWatcherService {

    private static final Logger log = LoggerFactory.getLogger(MappingFileWatcherService.class);

    private final Path workdir;
    private final long debounceSeconds;
    private final EtlTriggerService etlTriggerService;
    private final ScheduledExecutorService debounceExecutor = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "mapping-watch-debounce");
        t.setDaemon(true);
        return t;
    });
    private final Object debounceLock = new Object();
    private ScheduledFuture<?> pendingTrigger;

    public MappingFileWatcherService(
        @Value("${etl.workdir}") String workdir,
        @Value("${etl.debounce-seconds}") long debounceSeconds,
        EtlTriggerService etlTriggerService
    ) {
        this.workdir = Path.of(workdir).toAbsolutePath().normalize();
        this.debounceSeconds = debounceSeconds;
        this.etlTriggerService = etlTriggerService;
    }

    @PostConstruct
    public void start() {
        Thread watcherThread = new Thread(this::watchLoop, "mapping-file-watcher");
        watcherThread.setDaemon(true);
        watcherThread.start();
    }

    private void watchLoop() {
        try (WatchService watchService = FileSystems.getDefault().newWatchService()) {
            Set<Path> watchedDirs = new HashSet<>();
            for (MappingFile file : MappingFile.values()) {
                Path dir = workdir.resolve(file.relativePath()).getParent();
                if (watchedDirs.add(dir)) {
                    dir.register(watchService,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY);
                }
            }
            log.info("Overvåker {} mapping-kataloger for endringer i mapping.json", watchedDirs.size());

            while (!Thread.currentThread().isInterrupted()) {
                WatchKey key = watchService.take();
                boolean relevant = false;
                for (WatchEvent<?> event : key.pollEvents()) {
                    Object ctx = event.context();
                    if (ctx instanceof Path p && p.getFileName().toString().equals("mapping.json")) {
                        relevant = true;
                    }
                }
                key.reset();
                if (relevant) {
                    scheduleDebouncedTrigger();
                }
            }
        } catch (IOException e) {
            log.error("Klarte ikke å starte filovervåking av mapping-kataloger", e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private void scheduleDebouncedTrigger() {
        synchronized (debounceLock) {
            if (pendingTrigger != null) {
                pendingTrigger.cancel(false);
            }
            pendingTrigger = debounceExecutor.schedule(
                () -> etlTriggerService.trigger("mapping.json endret på disk"),
                debounceSeconds, TimeUnit.SECONDS);
        }
    }

    @PreDestroy
    public void stop() {
        debounceExecutor.shutdownNow();
    }
}
