package no.aktivkommune.masterdatabase.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;

// Body for update (PUT). No id: it comes from the path and cannot be changed,
// because it is the id shared with the kommune instances.
public record LokaletypeUpdate(
	@Schema(description = "Name of the venue type. Must be unique.", example = "Gymsal")
	@NotBlank String navn,

	@Schema(description = "Id of the parent venue type. Null or left out for a top-level venue type.", example = "12")
	Long parentId
)
{
}
