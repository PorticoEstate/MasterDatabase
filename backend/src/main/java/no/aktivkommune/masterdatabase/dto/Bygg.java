package no.aktivkommune.masterdatabase.dto;

// Ett byggkort i søkeresultatet.
// antallRessurser er antall bookbare ressurser i bygget som traff søket.
// avstandMeter er null når søket ikke er et nærhetssøk.

public record Bygg(
	Long id,
	String navn,
	String bydelNavn,
	String kommuneNavn,
	String adressetekst,
	String postnummer,
	String poststed,
	Double lat,
	Double lon,
	Double avstandMeter,
	int antallRessurser,
	String bookingUrl)
{
}
