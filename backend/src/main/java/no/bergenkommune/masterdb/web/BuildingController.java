package no.bergenkommune.masterdb.web;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import no.bergenkommune.masterdb.domain.Building;
import no.bergenkommune.masterdb.repository.BuildingRepository;

@RestController
public class BuildingController {

    private final BuildingRepository repository;

    public BuildingController(BuildingRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/buildings")
    public ResponseEntity<List<Building>> listBuildings(
        @RequestParam(required = false) String bydelNavn,
        @RequestParam(defaultValue = "50") int limit,
        @RequestParam(required = false) Long cursor
    ) {
        int boundedLimit = Math.min(Math.max(limit, 1), 500);
        List<Building> page = repository.list(bydelNavn, boundedLimit, cursor);

        ResponseEntity.BodyBuilder response = ResponseEntity.ok();
        if (page.size() == boundedLimit) {
            long nextCursor = page.get(page.size() - 1).byggId();
            response.header("X-Next-Cursor", String.valueOf(nextCursor));
        }
        return response.body(page);
    }
}
