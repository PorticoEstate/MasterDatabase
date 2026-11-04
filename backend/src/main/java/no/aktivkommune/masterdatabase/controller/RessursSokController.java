package no.aktivkommune.masterdatabase.controller;

import no.aktivkommune.masterdatabase.dto.RessursSokParametre;
import no.aktivkommune.masterdatabase.dto.SokFiltre;
import no.aktivkommune.masterdatabase.dto.SokSvar;
import no.aktivkommune.masterdatabase.service.RessursSokService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

// Søk på tvers av kommuner. Returnerer bare treff og lenker videre til det
// lokale bookingsystemet - ingen tilgjengelighet eller booking her.
//
// Søket skjer på serveren per tastetrykk (datamengden på tvers av kommuner er
// for stor til å laste ned til nettleseren slik de lokale sidene gjør), derfor
// gir /api/sok både bygg og ressurser i ett svar: én forespørsel per søk.
// Spring binder query-parametrene rett inn i RessursSokParametre; både
// ?aktivitet=A&aktivitet=B og ?aktivitet=A,B fungerer.
@RestController
@RequestMapping("/api/sok")
public class RessursSokController
{
	private final RessursSokService service;

	public RessursSokController(RessursSokService service)
	{
		this.service = service;
	}

	//
	@GetMapping
	public SokSvar sok(RessursSokParametre parametre)
	{
		return service.sok(parametre);
	}

	// Valgene i filterpanelet. Hentes én gang, ikke per tastetrykk.
	@GetMapping("/filtre")
	public SokFiltre filtre()
	{
		return service.hentFiltre();
	}
}



