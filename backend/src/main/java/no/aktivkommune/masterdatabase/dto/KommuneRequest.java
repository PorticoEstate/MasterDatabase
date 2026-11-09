package no.aktivkommune.masterdatabase.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

// Body for create (POST) and update (PUT). No id: it is server-owned and, for
// update, comes from the path. kommunenr is editable, so a renumbered kommune
// can be corrected through the API.
public record KommuneRequest(
	@Schema(description = "Kommune number, exactly 4 digits", example = "4601")
	@NotBlank @Pattern(regexp = "[0-9]{4}", message = "kommunenr must be 4 digits") String kommunenr,
	@Schema(description = "Kommune name", example = "Bergen")
	@NotBlank String navn,
	@Schema(description = "County name. Optional; null when left out.", example = "Vestland")
	String fylkesnavn
)
{
}
