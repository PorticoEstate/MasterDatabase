package no.aktivkommune.masterdatabase.dto;

// Ett ressurstreff slik frontend viser det i listen. Bare visningsfelt og
// lenker videre - interne id-er (kommune, bygg, instans) er utelatt.
// avstandMeter er null når søket ikke er et nærhetssøk.
public record RessursSokTreff(
	Long ressursId,
	String navn,
	String byggNavn,
	String kommuneNavn,
	String adressetekst,
	String postnummer,
	String poststed,
	String lokaletypeNavn,
	Double lat,
	Double lon,
	Double avstandMeter,
	String bookingUrl,
	String bildeUrl)
{
}
