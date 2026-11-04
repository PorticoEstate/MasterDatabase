package no.aktivkommune.masterdatabase.dto;

import java.util.List;

// Søkeparametrene fra klienten, bundet direkte fra query-strengen av Spring
// (?q=...&aktivitet=ACT-012&aktivitet=ACT-020). Samme record brukes av
// /api/sok/ressurser og /api/sok/bygg.
//
// Filtrene tar koder, ikke navn: navn er ikke unike på tvers av Norge (to
// kommuner heter Våler), kan omdøpes, og må URL-kodes. Brukeren ser bare navn;
// /api/sok/filtre gir kode+navn så frontend kan oversette.
//
// Wrapper-typer (Integer, ikke int) slik at utelatte parametre blir null og
// får standardverdi i RessursSokService.normaliser, i stedet for bindingsfeil.

public record RessursSokParametre(
	String q,
	List<String> kommune,      // kommunenr
	List<String> lokaletype,   // lokaletype.kode
	List<String> aktivitet,    // aktivitet.kode (ACT-xxx), ELLER mellom valgene
	List<String> fasilitet,    // fasilitet.kode, OG mellom valgene

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
