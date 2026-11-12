package no.aktivkommune.masterdatabase.dto;

import io.swagger.v3.oas.annotations.Parameter;

import java.util.List;

// Søkeparametrene fra klienten, bundet direkte fra query-strengen av Spring
// (?q=...&aktivitet=12&aktivitet=20). Samme record brukes av
// /masterdb/search (bygg- og ressursseksjonene).
//
// Filtrene tar kommunenr og id-er, ikke navn: navn kan omdøpes og må URL-kodes.
// Lokaletype, aktivitet og fasilitet har en delt id i kodeverket. Brukeren ser
// bare navn; /masterdb/search/filters/... gir id, navn og parentId så frontend
// kan oversette og bygge hierarkiet. Frontend sender selv med id-ene til alle
// undernivåer når en foreldrekategori er avhuket.
//
// Wrapper-typer (Integer, ikke int) slik at utelatte parametre blir null og
// får standardverdi i RessursSokService.normaliser, i stedet for bindingsfeil.
//
// @Parameter-beskrivelsene vises i Swagger UI (springdoc leser dem via
// @ParameterObject i controlleren). De er der for den som tester direkte;

public record RessursSokParametre(
	@Parameter(description = "Fritekst. Treffer navn, bygg, lokaletype, aktiviteter, fasiliteter og sted.")
	String q,

	@Parameter(description = "Kommunenummer (4 siffer), ikke navn. Gyldige verdier: kommuner[].kommunenr fra /masterdb/search/municipalities.")
	List<String> kommune,      // kommunenr

	@Parameter(description = "lokaletype.id. Gyldige verdier: id fra /masterdb/search/filters/resource-categories. ELLER mellom valgene.")
	List<Long> lokaletype,     // lokaletype.id, ELLER

	@Parameter(description = "aktivitet.id. Gyldige verdier: id fra /masterdb/search/filters/activities. ELLER mellom valgene. ")
	List<Long> aktivitet,      // aktivitet.id, ELLER

	@Parameter(description = "fasilitet.id. Gyldige verdier: id fra /masterdb/search/filters/facilities. ELLER mellom valgene.")
	List<Long> fasilitet,      // fasilitet.id, ELLER

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
