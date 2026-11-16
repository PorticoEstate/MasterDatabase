package no.aktivkommune.masterdatabase.dto;

import io.swagger.v3.oas.annotations.Parameter;

import java.util.List;

// Søkeparametrene til /masterdb/search (bygg- og ressursseksjonene).
// Rå input fra klienten som normaliseres og valideres i RessursSokService.mapParametere

// @Parameter-beskrivelsene vises i Swagger UI

public record RessursSokParametere(
	@Parameter(description = "Fritekst. Treffer navn, bygg, lokaletype, aktiviteter, fasiliteter og sted.")
	String fritekst,

	@Parameter(description = "Kommunenummer (4 siffer), ikke navn. Gyldige verdier: kommunenr fra /masterdb/search/filters/municipalities.")
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

	@Parameter(description = "relevans | avstand | navn. Standard: avstand ved nærhetssøk, relevans ved fritekst, ellers navn. relevans uten fritekst gir navn. avstand krever lat, lon og radiusMeter (ellers 400).")
	String sorter,             // relevans | avstand | navn
	@Parameter(description = "Sidenummer, 0-indeksert. side * storrelse kan maks være 50 000 (ellers 400).", example = "0")
	Integer side,              // 0-indeksert
	@Parameter(description = "Treff per side, standard 20, maks 100.", example = "20")
	Integer storrelse)
{
	public boolean harNarhet()
	{
		return lat != null && lon != null && radiusMeter != null;
	}
}
