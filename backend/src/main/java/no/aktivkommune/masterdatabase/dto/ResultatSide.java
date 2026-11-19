package no.aktivkommune.masterdatabase.dto;

import java.util.List;

// Én side med treff pluss totalantall, så frontend kan vise "x av y" og paginere.

public record ResultatSide<T>(
	List<T> treff,
	long totalt,
	int side,
	int storrelse)
{
}
