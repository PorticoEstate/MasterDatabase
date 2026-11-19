package no.aktivkommune.masterdatabase.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;

// Body for update (PUT). No id: it comes from the path and cannot be changed,
// because it is the id shared with the kommune instances.
public record AktivitetUpdate(
	@Schema(description = "Name of the activity. Must be unique.", example = "Svømming")
	@NotBlank String navn,

	@Schema(description = "Id of the parent activity. Null or left out for a top-level activity.", example = "12")
	Long parentId
)
{
}
