package no.bergenkommune.masterdb.domain;

import java.time.Instant;
import java.util.UUID;

/**
 * Status for én kjøring av "python3 etl/last_inn.py alle", trigget enten fra
 * admin-API-et eller av at en mapping.json-fil ble endret direkte.
 * Holdes kun i minnet (se EtlTriggerService) - ikke en egen databasetabell,
 * siden historikken ikke trenger å overleve en omstart av tjenesten.
 */
public final class EtlJobStatus {

    public enum State { RUNNING, SUCCESS, FAILED }

    private final String id = UUID.randomUUID().toString();
    private final String triggeredBy;
    private final Instant startedAt = Instant.now();
    private volatile Instant finishedAt;
    private volatile State state = State.RUNNING;
    private volatile String message = "Kjører...";

    public EtlJobStatus(String triggeredBy) {
        this.triggeredBy = triggeredBy;
    }

    public void markSuccess(String message) {
        this.state = State.SUCCESS;
        this.message = message;
        this.finishedAt = Instant.now();
    }

    public void markFailed(String message) {
        this.state = State.FAILED;
        this.message = message;
        this.finishedAt = Instant.now();
    }

    public String getId() { return id; }
    public String getTriggeredBy() { return triggeredBy; }
    public Instant getStartedAt() { return startedAt; }
    public Instant getFinishedAt() { return finishedAt; }
    public State getState() { return state; }
    public String getMessage() { return message; }
}
