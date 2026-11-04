package no.aktivkommune.masterdatabase.dto;

import java.util.List;

// Én side med treff pluss totalantall, så frontend kan vise "x av y" og
// paginere. totalt er 0 hvis siden ligger utenfor treffmengden.
public record SokeResultat<T>(
	List<T> treff,
	long totalt,
	int side,
	int storrelse)
{
}
