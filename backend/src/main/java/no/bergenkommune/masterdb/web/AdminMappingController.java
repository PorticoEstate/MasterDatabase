package no.bergenkommune.masterdb.web;

import java.io.IOException;
import java.util.Locale;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import no.bergenkommune.masterdb.domain.MappingFile;
import no.bergenkommune.masterdb.service.MappingFileService;

/**
 * Admin-endepunkt for å lese/oppdatere etl/*_mapping/mapping.json.
 * Trigger for ny last_inn.py-kjøring skjer IKKE herfra direkte, men av
 * MappingFileWatcherService som oppdager filendringen - samme vei uansett om
 * endringen kom herfra eller fra en vanlig fil-redigering.
 */
@RestController
@RequestMapping("/admin/mapping")
public class AdminMappingController {

    private final MappingFileService service;

    public AdminMappingController(MappingFileService service) {
        this.service = service;
    }

    @GetMapping("/{type}")
    public ResponseEntity<String> get(@PathVariable String type) throws IOException {
        MappingFile file = parse(type);
        return ResponseEntity.ok().contentType(MediaType.APPLICATION_JSON).body(service.read(file));
    }

    @PutMapping("/{type}")
    public ResponseEntity<Map<String, String>> put(@PathVariable String type, @RequestBody String json) {
        MappingFile file = parse(type);
        try {
            service.write(file, json);
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, e.getMessage(), e);
        } catch (IOException e) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "Klarte ikke å skrive filen", e);
        }
        return ResponseEntity.accepted().body(Map.of(
            "status", "lagret",
            "merknad", "En ny last_inn.py-kjøring trigges automatisk i løpet av få sekunder - "
                + "følg med på GET /admin/etl-jobs/latest"
        ));
    }

    private MappingFile parse(String type) {
        try {
            return MappingFile.valueOf(type.toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Ukjent mapping-type: " + type, e);
        }
    }
}
