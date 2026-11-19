package no.aktivkommune.masterdatabase.controller;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
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
import no.aktivkommune.masterdatabase.dto.AktivitetUpdate;
import no.aktivkommune.masterdatabase.service.AktivitetService;

// Administration of the aktivitet vocabulary, which the master owns. Every endpoint
// requires the X-API-KEY header (checked by ApiKeyFilter).
@RestController
@RequestMapping("/masterdb/aktivitet")
@Tag(name = "Aktivitet", description = "Update and delete aktiviteter. Requires an API key.")
@SecurityRequirement(name = "apiKey")
@ApiResponse(responseCode = "401", description = "Missing or invalid API key", content = @Content)
public class AktivitetController
{
	private final AktivitetService service;

	public AktivitetController(AktivitetService service)
	{
		this.service = service;
	}

	@Operation(summary = "Update an aktivitet",
			description = "Replaces navn and parentId. A parentId left out of the body is set to null, which makes "
					+ "the aktivitet top-level. The id cannot be changed.")
	@ApiResponses({
		@ApiResponse(responseCode = "400", description = "Invalid body (navn missing), parentId is the aktivitet itself, or no aktivitet with the given parentId", content = @Content),
		@ApiResponse(responseCode = "404", description = "No aktivitet with this id", content = @Content),
		@ApiResponse(responseCode = "409", description = "Another aktivitet already has this navn", content = @Content)
	})
	@PutMapping("/{id}")
	public void updateAktivitet(@PathVariable long id, @Valid @RequestBody AktivitetUpdate request)
	{
		service.update(id, request.navn(), request.parentId());
	}

	@Operation(summary = "Delete an aktivitet",
			description = "Also removes the links from resources to the aktivitet (ON DELETE CASCADE). An aktivitet "
					+ "that is the parent of others cannot be deleted. This cannot be undone.")
	@ApiResponses({
		@ApiResponse(responseCode = "404", description = "No aktivitet with this id", content = @Content),
		@ApiResponse(responseCode = "409", description = "The aktivitet is the parent of other aktiviteter", content = @Content)
	})
	@DeleteMapping("/{id}")
	@ResponseStatus(HttpStatus.NO_CONTENT)
	public void deleteAktivitet(@PathVariable long id)
	{
		service.delete(id);
	}
}
