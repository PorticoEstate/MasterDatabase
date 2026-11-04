package no.aktivkommune.masterdatabase.dto;

// Ett valg i filterpanelet: navn vises til brukeren, kode sendes tilbake som
// parameter til søket.
public record FilterValg(String kode, String navn)
{
}
