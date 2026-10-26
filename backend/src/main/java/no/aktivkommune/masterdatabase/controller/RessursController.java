package no.aktivkommune.masterdatabase.controller;

import no.aktivkommune.masterdatabase.dto.RessursDto;
import no.aktivkommune.masterdatabase.service.RessursService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/ressurser")
public class RessursController
{
	private final RessursService ressursService;

	public RessursController(RessursService ressursService)
	{
		this.ressursService = ressursService;
	}

	// 200 med ressursen, eller 404 hvis id-en ikke finnes.
	@GetMapping("/{id}")
	public ResponseEntity<RessursDto> hent(@PathVariable Long id)
	{
		return ressursService.hent(id)
			.map(ResponseEntity::ok)
			.orElseThrow(() -> new ResponseStatusException(
				HttpStatus.NOT_FOUND, "Fant ingen ressurs med id " + id));
	}
}
