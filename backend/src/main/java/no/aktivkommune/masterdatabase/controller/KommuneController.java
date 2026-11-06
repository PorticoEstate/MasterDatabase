package no.aktivkommune.masterdatabase.controller;

import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.tags.Tag;

@RestController
@RequestMapping("/masterdb/kommune")
@Tag(name = "Kommune-Endpoint", description = "Endpoint for CRUD operations on kommune.")
public class KommuneController {

	@PutMapping
	public String putKommune()
	{
		return "You got past the API-KEY Security";
	}
}
