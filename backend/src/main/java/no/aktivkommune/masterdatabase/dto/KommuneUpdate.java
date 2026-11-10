package no.aktivkommune.masterdatabase.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

// Body for update (PUT). No id: it comes from the path. kommunenr is editable, so
// a renumbered kommune can be corrected through the API. bookingBaseUrl is the one
// field that is not replaced: leaving it out keeps the current booking system.
public record KommuneUpdate(
	@Schema(description = "Kommune number, exactly 4 digits", example = "4601")
	@NotBlank @Pattern(regexp = "[0-9]{4}", message = "kommunenr must be 4 digits") String kommunenr,

	@Schema(description = "Kommune name", example = "Bergen")
	@NotBlank String navn,

	@Schema(description = "County name. Optional; null when left out.", example = "Vestland")
	String fylkesnavn,

	@Schema(description = "Base URL of the kommune's Aktiv kommune booking system. Optional. Leaving it out keeps the "
			+ "current booking system; an update never removes one. Can be set when the kommune has none, or repeated "
			+ "with the same URL (no change). A different URL than the registered one is rejected (409). Must be https://<name>.aktiv-kommune.no.",
			example = "https://bergen.aktiv-kommune.no")

	@Pattern(regexp = AktivKommuneUrl.REGEX, flags = Pattern.Flag.CASE_INSENSITIVE,
			message = "bookingBaseUrl must be https://<name>.aktiv-kommune.no") String bookingBaseUrl
)
{
}
