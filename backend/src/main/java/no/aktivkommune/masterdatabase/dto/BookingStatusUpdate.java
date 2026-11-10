package no.aktivkommune.masterdatabase.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;

// Body for PATCH /masterdb/kommune/{id}/booking.
public record BookingStatusUpdate(
	@Schema(description = "true: the booking system is included in the nightly sync. false: it is skipped, "
			+ "but the kommune and its data are kept.", example = "false")
	@NotNull Boolean aktiv
)
{
}
