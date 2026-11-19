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
import no.aktivkommune.masterdatabase.dto.LokaletypeUpdate;
import no.aktivkommune.masterdatabase.service.LokaletypeService;

// Administration of the lokaletype vocabulary, which the master owns. Every endpoint
// requires the X-API-KEY header (checked by ApiKeyFilter).
@RestController
@RequestMapping("/masterdb/lokaletype")
@Tag(name = "Lokaletype", description = "Update and delete lokaletyper. Requires an API key.")
@SecurityRequirement(name = "apiKey")
@ApiResponse(responseCode = "401", description = "Missing or invalid API key", content = @Content)
public class LokaletypeController
{
	private final LokaletypeService service;

	public LokaletypeController(LokaletypeService service)
	{
		this.service = service;
	}

	@Operation(summary = "Update a lokaletype",
			description = "Replaces navn and parentId. A parentId left out of the body is set to null, which makes "
					+ "the lokaletype top-level. The id cannot be changed.")
	@ApiResponses({
		@ApiResponse(responseCode = "400", description = "Invalid body (navn missing), parentId is the lokaletype itself, or no lokaletype with the given parentId", content = @Content),
		@ApiResponse(responseCode = "404", description = "No lokaletype with this id", content = @Content),
		@ApiResponse(responseCode = "409", description = "Another lokaletype already has this navn", content = @Content)
	})
	@PutMapping("/{id}")
	public void updateLokaletype(@PathVariable long id, @Valid @RequestBody LokaletypeUpdate request)
	{
		service.update(id, request.navn(), request.parentId());
	}

	@Operation(summary = "Delete a lokaletype",
			description = "Resources that have the lokaletype are kept, but lose it (lokaletype_id is set to null). A lokaletype "
					+ "that is the parent of others cannot be deleted. This cannot be undone.")
	@ApiResponses({
		@ApiResponse(responseCode = "404", description = "No lokaletype with this id", content = @Content),
		@ApiResponse(responseCode = "409", description = "The lokaletype is the parent of other lokaletyper", content = @Content)
	})
	@DeleteMapping("/{id}")
	@ResponseStatus(HttpStatus.NO_CONTENT)
	public void deleteLokaletype(@PathVariable long id)
	{
		service.delete(id);
	}
}
