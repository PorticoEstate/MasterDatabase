package no.aktivkommune.masterdatabase.dto;

// Ett ressurstreff slik frontend viser det i listen. Bare visningsfelt og
// lenker videre

public record Ressurs(
	Long id,
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
	String bookingUrl)
{
}
