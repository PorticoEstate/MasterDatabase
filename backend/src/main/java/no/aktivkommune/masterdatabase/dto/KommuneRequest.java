package no.aktivkommune.masterdatabase.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

// Body for create (POST) and update (PUT). No id: it is server-owned and, for
// update, comes from the path. kommunenr is editable, so a renumbered kommune
// can be corrected through the API.
public record KommuneRequest(
	@NotBlank @Pattern(regexp = "[0-9]{4}", message = "kommunenr must be 4 digits") String kommunenr,
	@NotBlank String navn,
	String fylkesnavn
)
{
}
