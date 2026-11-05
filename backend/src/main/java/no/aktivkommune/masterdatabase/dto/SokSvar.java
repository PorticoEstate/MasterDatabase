package no.aktivkommune.masterdatabase.dto;

// Svaret fra /masterdb/search: begge seksjonene på resultatsiden i ett kall, slik at
// frontend bare gjør én forespørsel per tastetrykk. Samme filter ligger til
// grunn for begge; bygg er ressurstreffene gruppert per bygg.
public record SokSvar(
	SokeResultat<ByggSokTreff> bygg,
	SokeResultat<RessursSokTreff> ressurser)
{
}
