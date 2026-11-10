package no.aktivkommune.masterdatabase.dto;

// Ett kommunevalg i filterpanelet: navn vises til brukeren, kommunenr
// sendes tilbake som parameter til søket.
// Lokaletype, aktivitet og fasilitet bruker FilterValg,
// siden kodeverkene identifiseres med id.
public record KommuneFilter(String kommunenr, String navn)
{
}
