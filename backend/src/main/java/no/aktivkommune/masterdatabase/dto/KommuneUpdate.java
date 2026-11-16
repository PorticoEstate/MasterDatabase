package no.aktivkommune.masterdatabase.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

// Body for update (PUT). No id: it comes from the path. kommunenr is editable, so
// a renumbered kommune can be corrected through the API. The booking system is not part
// of an update.
public record KommuneUpdate(
	@Schema(description = "Kommune number, exactly 4 digits", example = "4601")
	@NotBlank @Pattern(regexp = "[0-9]{4}", message = "kommunenr must be 4 digits") String kommunenr,

	@Schema(description = "Kommune name", example = "Bergen")
	@NotBlank String navn,

	@Schema(description = "County name. Optional; null when left out.", example = "Vestland")
	String fylkesnavn
)
{
}
