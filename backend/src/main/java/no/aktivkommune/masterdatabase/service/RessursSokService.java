package no.aktivkommune.masterdatabase.service;

import no.aktivkommune.masterdatabase.dto.ByggSokTreff;
import no.aktivkommune.masterdatabase.dto.FilterValg;
import no.aktivkommune.masterdatabase.dto.KommuneFilter;
import no.aktivkommune.masterdatabase.dto.RessursSokParametre;
import no.aktivkommune.masterdatabase.dto.RessursSokTreff;
import no.aktivkommune.masterdatabase.dto.RessursSokSvar;
import no.aktivkommune.masterdatabase.dto.SokeResultat;
import no.aktivkommune.masterdatabase.repository.RessursSokRepository;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Locale;

// Validerer og normaliserer søkeparametrene før de når SQL-en, slik at
// repositoryet kan stole på at listene aldri er null, sidestørrelsen er
// begrenset og sorteringen er en av de kjente verdiene.
@Service
public class RessursSokService
{
	static final int STANDARD_STORRELSE = 20;
	static final int MAKS_STORRELSE = 100;
	static final int MAKS_RADIUS_METER = 50_000;
	static final long MAKS_OFFSET = 50_000;

	private final RessursSokRepository repository;

	public RessursSokService(RessursSokRepository repository)
	{
		this.repository = repository;
	}

	// Det controlleren bruker: normaliserer én gang og kjører begge søkene i
	// samme transaksjon, så bygg og ressurser er hentet fra samme øyeblikk.
	@Transactional(readOnly = true)
	public RessursSokSvar sok(RessursSokParametre input)
		{
		RessursSokParametre p = normaliser(input);
		return new RessursSokSvar(
				repository.sokBygg(p),
				repository.sokRessurser(p));
		}

	@Transactional(readOnly = true)
	public SokeResultat<RessursSokTreff> sokRessurser(RessursSokParametre input)
	{
		return repository.sokRessurser(normaliser(input));
	}

	@Transactional(readOnly = true)
	public SokeResultat<ByggSokTreff> sokBygg(RessursSokParametre input)
	{
		return repository.sokBygg(normaliser(input));
	}

	@Transactional (readOnly = true)
	public List<KommuneFilter> hentKommuner(){
		return repository.hentKommuner();
	}

	@Transactional (readOnly = true)
	public List<FilterValg> hentAktiviteter() {
		return repository.hentAktiviteter();
	}

	@Transactional (readOnly = true)
	public List<FilterValg> hentFasiliteter() {
		return repository.hentFasiliteter();
	}


	@Transactional (readOnly = true)
	public List<FilterValg> hentLokaletyper() {
		return repository.hentLokaletyper();
	}

	// Pakkeprivat så den kan enhetstestes uten database.
	static RessursSokParametre normaliser(RessursSokParametre p)
	{
		String q = p.q() == null || p.q().isBlank() ? null : p.q().trim();

		// Et navn (?kommune=Bergen) ville ellers bare gitt tomt svar, som er
		// vanskelig å feilsøke.
		List<String> kommune = normaliserListe(p.kommune());
		for (String k : kommune)
		{
			if (!k.matches("\\d{4}"))
			{
				throw avvis("kommune må være et kommunenummer (4 siffer), f.eks. 4601 - ikke '" + k
					+ "'. Gyldige verdier finnes i /masterdb/search/filters/municipalities");
			}
		}

		boolean harLat = p.lat() != null;
		boolean harLon = p.lon() != null;
		boolean harRadius = p.radiusMeter() != null;
		if (harLat != harLon || (harLat && !harRadius) || (harRadius && !harLat))
		{
			throw avvis("lat, lon og radiusMeter må oppgis sammen");
		}
		if (harLat && (p.lat() < -90 || p.lat() > 90 || p.lon() < -180 || p.lon() > 180))
		{
			throw avvis("lat må være mellom -90 og 90, lon mellom -180 og 180");
		}
		if (harRadius && (p.radiusMeter() <= 0 || p.radiusMeter() > MAKS_RADIUS_METER))
		{
			throw avvis("radiusMeter må være mellom 1 og " + MAKS_RADIUS_METER);
		}

		// Standard sortering: avstand ved nærhetssøk, relevans ved fritekst,
		// ellers navn.
		String sorter = p.sorter() == null || p.sorter().isBlank()
			? (harLat ? "avstand" : q != null ? "relevans" : "navn")
			: p.sorter().trim().toLowerCase(Locale.ROOT);
		switch (sorter)
		{
			case "avstand" ->
			{
				if (!harLat)
				{
					throw avvis("sorter=avstand krever lat, lon og radiusMeter");
				}
			}
			case "relevans" ->
			{
				// Uten fritekst er alle like relevante; fall tilbake til navn.
				if (q == null)
				{
					sorter = "navn";
				}
			}
			case "navn" ->
			{
			}
			default -> throw avvis("sorter må være relevans, avstand eller navn");
		}

		int side = p.side() == null ? 0 : Math.max(0, p.side());
		int storrelse = p.storrelse() == null
			? STANDARD_STORRELSE
			: Math.min(MAKS_STORRELSE, Math.max(1, p.storrelse()));

		//Avvis dersom offset er urimelig stort
		long offset = (long) side * storrelse;

		if(offset > MAKS_OFFSET) {
			throw avvis("Side er for stor");
		}
		return new RessursSokParametre(
			q,
			kommune,
			normaliserIdListe(p.lokaletype()),
			normaliserIdListe(p.aktivitet()),
			normaliserIdListe(p.fasilitet()),
			p.lat(), p.lon(), p.radiusMeter(),
			sorter, side, storrelse);
	}

	// null -> tom liste, og blanke verdier (?aktivitet=) fjernes.
	private static List<String> normaliserListe(List<String> verdier)
	{
		if (verdier == null)
		{
			return List.of();
		}
		return verdier.stream()
			.filter(v -> v != null && !v.isBlank())
			.map(String::trim)
			.toList();
	}

	// null -> tom liste; dubletter fjernes.
	private static List<Long> normaliserIdListe(List<Long> verdier)
	{
		if (verdier == null)
		{
			return List.of();
		}
		return verdier.stream()
			.filter(v -> v != null)
			.distinct()
			.toList();
	}

	private static ResponseStatusException avvis(String melding)
	{
		return new ResponseStatusException(HttpStatus.BAD_REQUEST, melding);
	}
}
