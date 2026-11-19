package no.aktivkommune.masterdatabase.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;

// Body for update (PUT). No id: it comes from the path and cannot be changed,
// because it is the id shared with the kommune instances.
public record FasilitetUpdate(
	@Schema(description = "Name of the facility. Must be unique.", example = "Garderobe")
	@NotBlank String navn,

	@Schema(description = "Id of the parent facility. Null or left out for a top-level facility.", example = "12")
	Long parentId
)
{
}
