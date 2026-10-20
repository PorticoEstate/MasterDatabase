package no.bergenkommune.masterdb.service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import no.bergenkommune.masterdb.domain.MappingFile;

/**
 * Leser og skriver etl/*_mapping/mapping.json. Skriving valideres først, slik
 * at et admin-kall aldri kan sette last_inn.py i en tilstand der den ikke
 * klarer å lese fasitfilen (se etl/README.md for hva filene brukes til).
 */
@Service
public class MappingFileService {

    private final Path workdir;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public MappingFileService(@Value("${etl.workdir}") String workdir) {
        this.workdir = Path.of(workdir).toAbsolutePath().normalize();
    }

    public Path resolve(MappingFile file) {
        return workdir.resolve(file.relativePath());
    }

    public String read(MappingFile file) throws IOException {
        return Files.readString(resolve(file), StandardCharsets.UTF_8);
    }

    /**
     * Minimal strukturvalidering: gyldig JSON, objekt på toppnivå, med et
     * "values"-felt som selv er et objekt. Dekker ikke hvert enkelt
     * mapping-format i detalj, men fanger opp det som ville knekt
     * last_inn.py sin innlesing helt (ugyldig JSON, feil toppnivåtype).
     */
    public void validate(String json) {
        JsonNode root;
        try {
            root = objectMapper.readTree(json);
        } catch (IOException e) {
            throw new IllegalArgumentException("Ugyldig JSON: " + e.getMessage(), e);
        }
        if (!root.isObject()) {
            throw new IllegalArgumentException("Mapping-filen må være et JSON-objekt på toppnivå");
        }
        JsonNode values = root.get("values");
        if (values == null || !values.isObject()) {
            throw new IllegalArgumentException("Mapping-filen mangler et \"values\"-objekt");
        }
    }

    /** Skriver atomisk (temp-fil + move) slik at en samtidig lesing aldri ser en halvskrevet fil. */
    public void write(MappingFile file, String json) throws IOException {
        validate(json);
        Path target = resolve(file);
        Path tmp = target.resolveSibling(target.getFileName() + ".tmp");
        Files.writeString(tmp, json, StandardCharsets.UTF_8);
        Files.move(tmp, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
    }
}
