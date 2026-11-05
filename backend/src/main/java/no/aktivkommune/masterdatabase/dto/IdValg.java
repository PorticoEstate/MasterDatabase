package no.aktivkommune.masterdatabase.dto;

// Ett valg i filterpanelet for lokaletype, aktivitet og fasilitet: navn vises
// til brukeren, id sendes tilbake som parameter til søket. id er den delte
// nøkkelen i kodeverket (samme id i alle instanser).
public record IdValg(long id, String navn)
{
}
