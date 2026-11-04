package no.aktivkommune.masterdatabase.dto;

import java.util.List;

// Alle valgene i "More filters" i én respons. Bare verdier som faktisk er
// koblet til en bookbar ressurs, så panelet ikke viser tomme valg.
// Aktiviteter er en flat liste (ingen forelder/barn) inntil kodeverket er
// ferdig omarbeidet.
public record SokFiltre(
	List<FilterValg> kommuner,
	List<FilterValg> lokaletyper,
	List<FilterValg> aktiviteter,
	List<FilterValg> fasiliteter)
{
}


