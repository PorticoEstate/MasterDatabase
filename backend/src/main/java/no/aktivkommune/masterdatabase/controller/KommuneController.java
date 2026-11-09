package no.aktivkommune.masterdatabase.controller;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import no.aktivkommune.masterdatabase.dto.Kommune;
import no.aktivkommune.masterdatabase.dto.KommuneRequest;
import no.aktivkommune.masterdatabase.service.KommuneService;

@RestController
@RequestMapping("/masterdb/kommune")
@Tag(name = "Kommune-Endpoint", description = "Endpoint for CRUD operations on kommune.")
public class KommuneController
{
	private final KommuneService service;

	public KommuneController(KommuneService service)
	{
		this.service = service;
	}

	@GetMapping("/{id}")
	public Kommune getById(@PathVariable long id)
	{
		return service.getById(id);
	}

	@GetMapping
	public List<Kommune> getAll()
	{
		return service.getAll();
	}

	@PostMapping
	@ResponseStatus(HttpStatus.CREATED)
	public Kommune createKommune(@Valid @RequestBody KommuneRequest request)
	{
		return service.create(request.kommunenr(), request.navn(), request.fylkesnavn());
	}

	@PutMapping("/{id}")
	public void updateKommune(@PathVariable long id, @Valid @RequestBody KommuneRequest request)
	{
		service.update(id, request.kommunenr(), request.navn(), request.fylkesnavn());
	}

	@DeleteMapping("/{id}")
	@ResponseStatus(HttpStatus.NO_CONTENT)
	public void deleteKommune(@PathVariable long id)
	{
		service.delete(id);
	}
}
