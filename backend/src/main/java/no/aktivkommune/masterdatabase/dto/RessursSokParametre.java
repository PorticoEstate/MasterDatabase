package no.aktivkommune.masterdatabase.dto;

import java.util.List;

// Søkeparametrene fra klienten, bundet direkte fra query-strengen av Spring
// (?q=...&aktivitet=12&aktivitet=20). Samme record brukes av
// /api/sok/ressurser og /api/sok/bygg.
//
// Filtrene tar kommunenr og id-er, ikke navn: navn kan omdøpes og må URL-kodes.
// Lokaletype, aktivitet og fasilitet har en delt id i kodeverket. Brukeren ser
// bare navn; /api/sok/filtre gir kode/id + navn så frontend kan oversette.
//
// Wrapper-typer (Integer, ikke int) slik at utelatte parametre blir null og
// får standardverdi i RessursSokService.normaliser, i stedet for bindingsfeil.

public record RessursSokParametre(
	String q,
	List<String> kommune,      // kommunenr
	List<Long> lokaletype,     // lokaletype.id
	List<Long> aktivitet,      // aktivitet.id, ELLER mellom valgene
	List<Long> fasilitet,      // fasilitet.id, OG mellom valgene

	// Nærhetssøk. Alle tre må oppgis sammen.
	Double lat,
	Double lon,
	Integer radiusMeter,

	String sorter,             // relevans | avstand | navn
	Integer side,              // 0-indeksert
	Integer storrelse)
{
	public boolean harNarhet()
	{
		return lat != null && lon != null && radiusMeter != null;
	}
}
