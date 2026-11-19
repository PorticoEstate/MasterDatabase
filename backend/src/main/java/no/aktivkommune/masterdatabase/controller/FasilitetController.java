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
import no.aktivkommune.masterdatabase.dto.FasilitetUpdate;
import no.aktivkommune.masterdatabase.service.FasilitetService;

// Administration of the fasilitet vocabulary, which the master owns. Every endpoint
// requires the X-API-KEY header (checked by ApiKeyFilter).
@RestController
@RequestMapping("/masterdb/fasilitet")
@Tag(name = "Fasilitet", description = "Update and delete fasiliteter. Requires an API key.")
@SecurityRequirement(name = "apiKey")
@ApiResponse(responseCode = "401", description = "Missing or invalid API key", content = @Content)
public class FasilitetController
{
	private final FasilitetService service;

	public FasilitetController(FasilitetService service)
	{
		this.service = service;
	}

	@Operation(summary = "Update a fasilitet",
			description = "Replaces navn and parentId. A parentId left out of the body is set to null, which makes "
					+ "the fasilitet top-level. The id cannot be changed.")
	@ApiResponses({
		@ApiResponse(responseCode = "400", description = "Invalid body (navn missing), parentId is the fasilitet itself, or no fasilitet with the given parentId", content = @Content),
		@ApiResponse(responseCode = "404", description = "No fasilitet with this id", content = @Content),
		@ApiResponse(responseCode = "409", description = "Another fasilitet already has this navn", content = @Content)
	})
	@PutMapping("/{id}")
	public void updateFasilitet(@PathVariable long id, @Valid @RequestBody FasilitetUpdate request)
	{
		service.update(id, request.navn(), request.parentId());
	}

	@Operation(summary = "Delete a fasilitet",
			description = "Also removes the links from resources to the fasilitet (ON DELETE CASCADE). A fasilitet "
					+ "that is the parent of others cannot be deleted. This cannot be undone.")
	@ApiResponses({
		@ApiResponse(responseCode = "404", description = "No fasilitet with this id", content = @Content),
		@ApiResponse(responseCode = "409", description = "The fasilitet is the parent of other fasiliteter", content = @Content)
	})
	@DeleteMapping("/{id}")
	@ResponseStatus(HttpStatus.NO_CONTENT)
	public void deleteFasilitet(@PathVariable long id)
	{
		service.delete(id);
	}
}
