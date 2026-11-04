package no.aktivkommune.masterdatabase.dto;

// Ett kommunevalg i filterpanelet: navn vises til brukeren, kode (kommunenr)
// sendes tilbake som parameter til søket. Lokaletype, aktivitet og fasilitet
// bruker IdValg, siden kodeverkene identifiseres med id.
public record FilterValg(String kode, String navn)
{
}
