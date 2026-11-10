package no.aktivkommune.masterdatabase.controller;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import no.aktivkommune.masterdatabase.dto.BookingStatusUpdate;
import no.aktivkommune.masterdatabase.dto.Kommune;
import no.aktivkommune.masterdatabase.dto.KommuneCreate;
import no.aktivkommune.masterdatabase.dto.KommuneUpdate;
import no.aktivkommune.masterdatabase.service.KommuneService;

// Administration of kommuner. Every endpoint requires the X-API-KEY header
// (checked by ApiKeyFilter); "apiKey" is the scheme declared in OpenApiConfig.
@RestController
@RequestMapping("/masterdb/kommune")
@Tag(name = "Kommune", description = "Create, read, update and delete kommuner. Requires an API key.")
@SecurityRequirement(name = "apiKey")
@ApiResponse(responseCode = "401", description = "Missing or invalid API key", content = @Content)
public class KommuneController
{
	private final KommuneService service;

	public KommuneController(KommuneService service)
	{
		this.service = service;
	}

	@Operation(summary = "Get a kommune by id")
	@ApiResponse(responseCode = "404", description = "No kommune with this id", content = @Content)
	@GetMapping("/{id}")
	public Kommune getById(@PathVariable long id)
	{
		return service.getById(id);
	}

	@Operation(summary = "List all kommuner",
			description = "All kommuner, ordered by name. bookingBaseUrl and bookingAktiv show which kommuner the nightly sync loads data for (those with a booking system that is active).")
	@GetMapping
	public List<Kommune> getAll()
	{
		return service.getAll();
	}

	@Operation(summary = "Create a kommune",
			description = "Returns the created kommune including its generated id. bookingBaseUrl "
					+ "(https://<name>.aktiv-kommune.no) is required: the kommune's Aktiv kommune booking system is "
					+ "registered, active, in the same call, and the next nightly sync loads the kommune's data from it.")
	@ApiResponses({
		@ApiResponse(responseCode = "400", description = "Invalid body (kommunenr not 4 digits, navn missing, or bookingBaseUrl missing or not https://<name>.aktiv-kommune.no)", content = @Content),
		@ApiResponse(responseCode = "409", description = "kommunenr already exists, or bookingBaseUrl is registered for another kommune", content = @Content)
	})
	@PostMapping
	@ResponseStatus(HttpStatus.CREATED)
	public Kommune createKommune(@Valid @RequestBody KommuneCreate request)
	{
		return service.create(request.kommunenr(), request.navn(), request.fylkesnavn(), request.bookingBaseUrl());
	}

	@Operation(summary = "Update a kommune",
			description = "Replaces kommunenr, navn and fylkesnavn. A fylkesnavn left out of the body is set to null. "
					+ "kommunenr can be changed here, e.g. when a kommune is renumbered. bookingBaseUrl is optional: "
					+ "leaving it out keeps the current booking system (an update never removes one). Giving it "
					+ "registers the booking system if the kommune has none, so the next nightly sync loads the "
					+ "kommune; repeating the registered URL changes nothing. To stop or resume syncing, use "
					+ "PATCH /{id}/booking.")
	@ApiResponses({
		@ApiResponse(responseCode = "400", description = "Invalid body (kommunenr not 4 digits, navn missing, or bookingBaseUrl not https://<name>.aktiv-kommune.no)", content = @Content),
		@ApiResponse(responseCode = "404", description = "No kommune with this id", content = @Content),
		@ApiResponse(responseCode = "409", description = "Another kommune already has this kommunenr; bookingBaseUrl is registered for another kommune; or the kommune already has a different booking system", content = @Content)
	})
	@PutMapping("/{id}")
	public void updateKommune(@PathVariable long id, @Valid @RequestBody KommuneUpdate request)
	{
		service.update(id, request.kommunenr(), request.navn(), request.fylkesnavn(), request.bookingBaseUrl());
	}

	@Operation(summary = "Include or exclude the booking system in the sync",
			description = "Sets whether the nightly sync loads data for this kommune. aktiv=false stops the sync "
					+ "but keeps the kommune and its data; aktiv=true resumes it. Idempotent. Returns the kommune.")
	@ApiResponses({
		@ApiResponse(responseCode = "400", description = "aktiv missing", content = @Content),
		@ApiResponse(responseCode = "404", description = "No kommune with this id", content = @Content),
		@ApiResponse(responseCode = "409", description = "The kommune has no booking system", content = @Content)
	})
	@PatchMapping("/{id}/booking")
	public Kommune setBookingAktiv(@PathVariable long id, @Valid @RequestBody BookingStatusUpdate request)
	{
		return service.setBookingAktiv(id, request.aktiv());
	}

	@Operation(summary = "Delete a kommune",
			description = "Also deletes everything that belongs to the kommune: buildings, addresses, streets and "
					+ "resources (ON DELETE CASCADE), and its booking system registration unless another kommune "
					+ "uses it. This cannot be undone.")
	@ApiResponse(responseCode = "404", description = "No kommune with this id", content = @Content)
	@DeleteMapping("/{id}")
	@ResponseStatus(HttpStatus.NO_CONTENT)
	public void deleteKommune(@PathVariable long id)
	{
		service.delete(id);
	}
}
