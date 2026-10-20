package no.bergenkommune.masterdb.web;

import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import no.bergenkommune.masterdb.domain.EtlJobStatus;
import no.bergenkommune.masterdb.service.EtlTriggerService;

/**
 * Status/historikk for last_inn.py-kjøringer, pluss en manuell "trigg nå"-
 * knapp for å teste kjeden uten å måtte vente på debounce etter en
 * mapping.json-endring.
 */
@RestController
@RequestMapping("/admin/etl-jobs")
public class EtlJobStatusController {

    private final EtlTriggerService service;

    public EtlJobStatusController(EtlTriggerService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<EtlJobStatus> triggerNow() {
        EtlJobStatus job = service.trigger("admin-api: manuell trigger");
        return ResponseEntity.accepted().body(job);
    }

    @GetMapping("/latest")
    public ResponseEntity<EtlJobStatus> latest() {
        EtlJobStatus job = service.latest();
        return job == null ? ResponseEntity.noContent().build() : ResponseEntity.ok(job);
    }

    @GetMapping
    public List<EtlJobStatus> history() {
        return service.history();
    }
}
