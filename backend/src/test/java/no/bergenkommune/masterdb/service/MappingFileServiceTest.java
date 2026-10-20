package no.bergenkommune.masterdb.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import no.bergenkommune.masterdb.domain.MappingFile;

/**
 * Dekker selve admin-skrive-flyten (uten Spring-kontekst eller database):
 * at en gyldig mapping-oppdatering faktisk havner på disk, og at en ugyldig
 * en aldri gjør det - siden det er nøyaktig det som ville knekt last_inn.py
 * sin innlesing av fasitfilen.
 */
class MappingFileServiceTest {

    @TempDir
    Path tempDir;

    private MappingFileService service;

    @BeforeEach
    void setUp() throws IOException {
        for (MappingFile file : MappingFile.values()) {
            Path path = tempDir.resolve(file.relativePath());
            Files.createDirectories(path.getParent());
            Files.writeString(path, "{\"values\":{}}");
        }
        service = new MappingFileService(tempDir.toString());
    }

    @Test
    void writesAndReadsBackAValidMapping() throws IOException {
        service.write(MappingFile.LOKALETYPE, "{\"values\":{\"gymsal\":\"GYMSAL\"}}");

        assertThat(service.read(MappingFile.LOKALETYPE)).contains("GYMSAL");
    }

    @Test
    void rejectsAMappingWithoutAValuesField() {
        assertThrows(IllegalArgumentException.class,
            () -> service.write(MappingFile.LOKALETYPE, "{\"foo\":1}"));
    }

    @Test
    void rejectsInvalidJson() {
        assertThrows(IllegalArgumentException.class,
            () -> service.write(MappingFile.LOKALETYPE, "ikke json"));
    }

    @Test
    void doesNotTouchTheFileWhenValidationFails() throws IOException {
        String original = service.read(MappingFile.FASILITET);

        assertThrows(IllegalArgumentException.class,
            () -> service.write(MappingFile.FASILITET, "[]"));

        assertThat(service.read(MappingFile.FASILITET)).isEqualTo(original);
    }
}
