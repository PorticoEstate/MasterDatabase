package no.aktivkommune.masterdatabase.dto;

import io.swagger.v3.oas.annotations.Parameter;

import java.util.List;

// Søkeparametrene fra klienten, bundet direkte fra query-strengen av Spring
// (?q=...&aktivitet=12&aktivitet=20). Samme record brukes av
// /masterdb/search (bygg- og ressursseksjonene).
//
// Filtrene tar kommunenr og id-er, ikke navn: navn kan omdøpes og må URL-kodes.
// Lokaletype, aktivitet og fasilitet har en delt id i kodeverket. Brukeren ser
// bare navn; /masterdb/search/filter gir kode/id + navn så frontend kan oversette.
//
// Wrapper-typer (Integer, ikke int) slik at utelatte parametre blir null og
// får standardverdi i RessursSokService.normaliser, i stedet for bindingsfeil.
//
// @Parameter-beskrivelsene vises i Swagger UI (springdoc leser dem via
// @ParameterObject i controlleren). De er der for den som tester direkte;
// frontend sender alltid kode/id fra filter-endepunktet.

public record RessursSokParametre(
	@Parameter(description = "Fritekst. Treffer navn, bygg, lokaletype, aktiviteter, fasiliteter og sted.",
		example = "badminton")
	String q,

	@Parameter(description = "Kommunenummer (4 siffer), ikke navn. Gyldige verdier: kommuner[].kode fra /masterdb/search/filter.",
		example = "4601")
	List<String> kommune,      // kommunenr

	@Parameter(description = "lokaletype.id. Gyldige verdier: lokaletyper[].id fra /masterdb/search/filter.")
	List<Long> lokaletype,     // lokaletype.id

	@Parameter(description = "aktivitet.id. Gyldige verdier: aktiviteter[].id fra /masterdb/search/filter. ELLER mellom valgene.")
	List<Long> aktivitet,      // aktivitet.id, ELLER mellom valgene

	@Parameter(description = "fasilitet.id. Gyldige verdier: fasiliteter[].id fra /masterdb/search/filter. OG mellom valgene.")
	List<Long> fasilitet,      // fasilitet.id, OG mellom valgene

	// Nærhetssøk. Alle tre må oppgis sammen.
	@Parameter(description = "Breddegrad for nærhetssøk. Krever lon og radiusMeter.", example = "60.39")
	Double lat,
	@Parameter(description = "Lengdegrad for nærhetssøk. Krever lat og radiusMeter.", example = "5.32")
	Double lon,
	@Parameter(description = "Radius i meter rundt lat/lon, maks 50 000.", example = "5000")
	Integer radiusMeter,

	@Parameter(description = "relevans | avstand | navn. Standard: avstand ved nærhetssøk, relevans ved fritekst, ellers navn.")
	String sorter,             // relevans | avstand | navn
	@Parameter(description = "Sidenummer, 0-indeksert.", example = "0")
	Integer side,              // 0-indeksert
	@Parameter(description = "Treff per side, standard 20, maks 100.", example = "20")
	Integer storrelse)
{
	public boolean harNarhet()
	{
		return lat != null && lon != null && radiusMeter != null;
	}
}
