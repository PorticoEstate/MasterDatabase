package no.aktivkommune.masterdatabase.controller;

import no.aktivkommune.masterdatabase.dto.FilterValg;
import no.aktivkommune.masterdatabase.dto.KommuneFilter;
import no.aktivkommune.masterdatabase.dto.RessursSokParametere;
import no.aktivkommune.masterdatabase.dto.ByggOgRessursResultat;
import no.aktivkommune.masterdatabase.service.RessursSokService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

// Søk på tvers av kommuner. Returnerer bare treff og lenker videre til det
// lokale bookingsystemet - ingen tilgjengelighet eller booking her.

// Søket skjer på serveren per tastetrykk (datamengden på tvers av kommuner er
// for stor til å laste ned til nettleseren slik de lokale sidene gjør), derfor
// gir /masterdb/search både bygg og ressurser i ett svar: én forespørsel per søk.

@RestController
@RequestMapping("/masterdb/search")
@Tag(name = "Search", description = "Search active resources and buildings with matching resources.")
public class RessursSokController
{
	private final RessursSokService service;

	public RessursSokController(RessursSokService service)
	{
		this.service = service;
	}

	@Operation(summary = "Search resources and buildings with at least one resource",
			description = "Free-text search with filters (municipality, venue type, activity, facility) "
					+ "and optional radius around a point. Returns building cards and a resource list. "
					+ "Sort by relevans, avstand or navn; paginate with side and storrelse. "
					+ "Never checks availability or books anything.")
	@GetMapping
	public ByggOgRessursResultat sok(@ParameterObject RessursSokParametere parametre)
	{
		return service.sok(parametre);
	}

	//Valgmuligheter for kommunefilteret.
	@Operation (summary = "Municipalities (municipality number + name) that are linked to a bookable resource")
	@GetMapping ("/filters/municipalities")
	public List<KommuneFilter> getMunicipalities()
	{
		return service.hentKommuner();
	}

	//Valgmuligheter for aktivitetsfilteret (alle aktiviteter).
	@Operation (summary = "All activities (id, name, parentId)",
			description = "Every row in the activity table, including top-level categories "
					+ "(parentId = null). The client builds the tree and sends the ids of all "
					+ "descendants when a parent is selected in the search.")
	@GetMapping ("/filters/activities")
	public List<FilterValg> getActivities()
	{
		return service.hentAktiviteter();
	}

	//Valgmuligheter for fasilitetsfilteret (alle fasiliteter).
	@Operation (summary = "All facilities (id, name, parentId)",
			description = "Every row in the facility table, including top-level categories "
					+ "(parentId = null). The client builds the tree and sends the ids of all "
					+ "descendants when a parent is selected in the search.")
	@GetMapping ("/filters/facilities")
	public List<FilterValg> getFacilities()
	{
		return service.hentFasiliteter();
	}

	//Valgmuligheter for lokaletypefilteret (alle lokaletyper).
	@Operation (summary = "All venue types (id, name, parentId)",
			description = "Every row in the venue type table, including top-level categories "
					+ "(parentId = null). The client builds the tree and sends the ids of all "
					+ "descendants when a parent is selected in the search.")
	@GetMapping ("/filters/resource-categories")
	public List<FilterValg> getResourceCategories()
	{
		return service.hentLokaletyper();
	}


}



