package no.aktivkommune.masterdatabase.dto;

// Ett byggkort ("Buildings and facilities"). antallRessurser er antall
// bookbare ressurser i bygget som traff søket. bookingUrl er null
// for bygg som bare er kjent fra matrikkelen (ingen ekstern_id).
public record ByggSokTreff(
	Long byggId,
	String byggNavn,
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
