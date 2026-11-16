package no.aktivkommune.masterdatabase.service;

import no.aktivkommune.masterdatabase.dto.FilterValg;
import no.aktivkommune.masterdatabase.dto.KommuneFilter;
import no.aktivkommune.masterdatabase.dto.RessursSokParametere;
import no.aktivkommune.masterdatabase.dto.ByggOgRessursResultat;
import no.aktivkommune.masterdatabase.repository.FilterRepository;
import no.aktivkommune.masterdatabase.repository.RessursSokRepository;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import java.util.List;

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

	private final RessursSokRepository ressursRepository;
	private final FilterRepository filterRepository;

	public RessursSokService(RessursSokRepository ressursRepository, FilterRepository filterRepository)
	{
		this.ressursRepository = ressursRepository;
		this.filterRepository = filterRepository;
	}

	// Input er rå-parametrene som normaliseres og valideres
	@Transactional(readOnly = true)
	public ByggOgRessursResultat sok(RessursSokParametere parametere)
		{
		RessursSokParametere p = mapParametere(parametere);
		return new ByggOgRessursResultat(
				ressursRepository.sokBygg(p),
				ressursRepository.sokRessurser(p));
		}

	static RessursSokParametere mapParametere(RessursSokParametere p)
	{
		//Validerer og klargjør parameterdata som er skrevet inn
		String fritekst = p.fritekst() == null || p.fritekst().isBlank() ? null : p.fritekst().trim();
		boolean harFritekst = fritekst != null;
		boolean harNarhet = p.harNarhet();

		validerKommuner(p.kommune());
		validerPosisjon(p);

		String sorter = p.sorter() == null || p.sorter().isBlank() ?
		null : p.sorter().trim().toLowerCase();

		if(sorter==null) {
			if(harNarhet) sorter = "avstand";
			else if(harFritekst) sorter = "relevans";
			else sorter = "navn";
		}

		validerSorter(sorter, harNarhet);

		// Uten fritekst er alle like relevante; fall tilbake til navn.
		boolean sorterErRelevans = sorter.equals("relevans");
		if(sorterErRelevans && !harFritekst) {
				sorter = "navn";
				}

		//paginering
		int side = p.side() == null ? 0 : Math.max(0, p.side());
		int storrelse = p.storrelse() == null
			? STANDARD_STORRELSE
			: Math.min(MAKS_STORRELSE, Math.max(1, p.storrelse()));

		//Avvis dersom offset er urimelig stort
		long offset = (long) side * storrelse;
		validerOffset(offset);

		return new RessursSokParametere(
			fritekst,
			normaliserKommuneListe(p.kommune()),
			normaliserFilterListe(p.lokaletype()),
			normaliserFilterListe(p.aktivitet()),
			normaliserFilterListe(p.fasilitet()),
			p.lat(), p.lon(), p.radiusMeter(),
			sorter, side, storrelse);
	}

	// null -> tom liste, og blanke verdier fjernes. Da gir "ingen valg" et søk uten filter
	private static List<String> normaliserKommuneListe(List<String> verdier)
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
	private static List<Long> normaliserFilterListe(List<Long> verdier)
	{
		if (verdier == null)
		{
			return List.of();
		}
		return verdier.stream()
			.filter(v -> v != null)  //fjerner tomme elementer i listen
			.distinct()
			.toList();
	}

	private static ResponseStatusException avvis(String melding)
	{
		return new ResponseStatusException(HttpStatus.BAD_REQUEST, melding);
	}

	//Validerer posisjonsparametre
	private static void validerPosisjon(RessursSokParametere p){
		boolean harLat = p.lat() != null;
		boolean harLon = p.lon() != null;
		boolean harRadius = p.radiusMeter() != null;

		boolean ufullstendigPosisjon =  harLat != harLon || (harLat && !harRadius) || (harRadius && !harLat);
		if (ufullstendigPosisjon)
		{
			throw avvis("lat, lon og radiusMeter må oppgis sammen");
		}

		boolean utenforPosisjonGrense = harLat && (p.lat() < -90 || p.lat() > 90 || p.lon() < -180 || p.lon() > 180);
		if (utenforPosisjonGrense)
		{
			throw avvis("lat må være mellom -90 og 90, lon mellom -180 og 180");
		}

		boolean utenforRadius = harRadius && (p.radiusMeter() <= 0 || p.radiusMeter() > MAKS_RADIUS_METER);
		if (utenforRadius)
		{
			throw avvis("radiusMeter må være mellom 1 og " + MAKS_RADIUS_METER);
		}
	}

	private static void validerKommuner(List<String> kommuner){
		// Et navn (?kommune=Bergen) ville ellers bare gitt tomt svar, som er
		// vanskelig å feilsøke.
		List<String> kommune = normaliserKommuneListe(kommuner);
		for (String k : kommune)
		{
			if (!k.matches("\\d{4}"))
			{
				throw avvis("kommune må være et kommunenummer (4 siffer). Gyldige verdier finnes i /masterdb/search/filters/municipalities");
			}
		}
	}

	private static void validerSorter(String sorter, boolean harNarhet){
		boolean erRiktigType = sorter.equals("relevans") || sorter.equals("navn") || sorter.equals("avstand");
		if(!erRiktigType) {
			throw avvis("sorter må være relevans, avstand eller navn");
		}
		if(sorter.equals("avstand") && !harNarhet){
			throw avvis("sorter=avstand krever lat, lon og radiusMeter");
		}
	}

	private static void validerOffset(long offset) {
		if(offset > MAKS_OFFSET) {
			throw avvis("Side er for stor");
		}
	}

	//Filtervalg
	@Transactional (readOnly = true)
	public List<KommuneFilter> hentKommuner(){
		return filterRepository.hentKommuner();
	}

	@Transactional (readOnly = true)
	public List<FilterValg> hentAktiviteter() {
		return filterRepository.hentAktiviteter();
	}

	@Transactional (readOnly = true)
	public List<FilterValg> hentFasiliteter() {
		return filterRepository.hentFasiliteter();
	}

	@Transactional (readOnly = true)
	public List<FilterValg> hentLokaletyper() {
		return filterRepository.hentLokaletyper();
	}
}
