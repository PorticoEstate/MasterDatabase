package no.aktivkommune.masterdatabase.controller;

import no.aktivkommune.masterdatabase.dto.RessursSokParametre;
import no.aktivkommune.masterdatabase.dto.SokFiltre;
import no.aktivkommune.masterdatabase.dto.SokSvar;
import no.aktivkommune.masterdatabase.service.RessursSokService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

// Søk på tvers av kommuner. Returnerer bare treff og lenker videre til det
// lokale bookingsystemet - ingen tilgjengelighet eller booking her.
//
// Søket skjer på serveren per tastetrykk (datamengden på tvers av kommuner er
// for stor til å laste ned til nettleseren slik de lokale sidene gjør), derfor
// gir /masterdb/search både bygg og ressurser i ett svar: én forespørsel per søk.
// Spring binder query-parametrene rett inn i RessursSokParametre; både
// ?aktivitet=A&aktivitet=B og ?aktivitet=A,B fungerer.
@RestController
@RequestMapping("/masterdb/search")
@Tag(name = "Search", description = "Search across municipalities")
public class RessursSokController
{
	private final RessursSokService service;

	public RessursSokController(RessursSokService service)
	{
		this.service = service;
	}

	@Operation(summary = "Search buildings and resources",
			description = "Free-text search with filters (municipality, venue type, activity, facility) "
					+ "and optional radius around a point. Returns building cards and a resource list. "
					+ "Never checks availability or books anything.")
	@GetMapping
	public SokSvar sok(@ParameterObject RessursSokParametre parametre)
	{
		return service.sok(parametre);
	}

	// Valgene i filterpanelet. Hentes én gang, ikke per tastetrykk.
	@Operation(summary = "List filter options",
			description = "Municipalities (code + name) and venue types, activities and facilities (id + name) "
					+ "that are linked to a bookable resource.")
	@GetMapping("/filter")
	public SokFiltre filtre()
	{
		return service.hentFiltre();
	}
}



