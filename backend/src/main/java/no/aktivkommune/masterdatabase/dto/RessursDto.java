package no.aktivkommune.masterdatabase.dto;

import java.math.BigDecimal;
import java.time.OffsetDateTime;

// Det API-et returnerer, adskilt fra entiteten. Returnerer vi entiteten direkte,
// prøver Jackson å serialisere lazy-proxyen for lokaletype og feiler.
// Alle kolonner unntatt sokevektor, som bare er nyttig inne i en søkespørring.
public record RessursDto(
	Long id,
	Long fagsystemInstansId,
	String eksternId,
	Long kommuneId,
	Long bygningId,
	String navn,
	Long lokaletypeId,
	String lokaletypeKode,
	String lokaletypeNavn,
	Integer kapasitet,
	BigDecimal arealM2,
	String beskrivelse,
	boolean aktiv,
	boolean bookbar,
	OffsetDateTime sistOppdatert,
	OffsetDateTime createdAt,
	OffsetDateTime updatedAt)
{
}
