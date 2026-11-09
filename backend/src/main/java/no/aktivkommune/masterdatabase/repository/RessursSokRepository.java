package no.aktivkommune.masterdatabase.repository;

import no.aktivkommune.masterdatabase.dto.ByggSokTreff;
import no.aktivkommune.masterdatabase.dto.KommuneFilter;
import no.aktivkommune.masterdatabase.dto.FilterValg;
import no.aktivkommune.masterdatabase.dto.RessursSokParametre;
import no.aktivkommune.masterdatabase.dto.RessursSokTreff;
import no.aktivkommune.masterdatabase.dto.SokFiltre;
import no.aktivkommune.masterdatabase.dto.SokeResultat;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

// All SQL for søket, mot v_ressurs_sok. JdbcClient i stedet for JPA fordi alt
// som gjør søket nyttig er Postgres-spesifikt (tsvector/@@, pg_trgm, PostGIS
// ST_DWithin, array-operatorene && og @>) og viewet er skrivebeskyttet - JPA
// ville bare vært et lag å oversette gjennom. Når søket feiler eller er tregt,
// kan spørringen under limes rett inn i psql med EXPLAIN ANALYZE.
//
// Brukerinput går alltid som navngitte parametre (:q, :kommune, ...), aldri
// inn i SQL-strengen. Det eneste dynamiske er hvilke faste fragmenter som tas
// med, og ORDER BY velges fra en lukket liste - det hindrer SQL-injeksjon.
@Repository
public class RessursSokRepository
{
	// ST_MakePoint tar lon først, så lat.
	private static final String PUNKT = "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography";

	private final JdbcClient jdbc;

	public RessursSokRepository(JdbcClient jdbc)
	{
		this.jdbc = jdbc;
	}

	public SokeResultat<RessursSokTreff> sokRessurser(RessursSokParametre p)
	{
		Treff t = treff(p);
		String sql = t.sql() + """

			SELECT ressurs_id, navn, bygg_navn, kommune_navn, adressetekst, postnummer, poststed,
			       lokaletype_navn, lat, lon, avstand, booking_url, bilde_url,
			       count(*) OVER () AS totalt
			  FROM treff
			 ORDER BY\s""" + switch (p.sorter())
			{
				case "relevans" -> "rang DESC, navn";
				case "avstand" -> "avstand, navn";
				default -> "navn";
			} + ", ressurs_id LIMIT :limit OFFSET :offset";

		return kjor(sql, t, p, rs -> new RessursSokTreff(
			rs.getLong("ressurs_id"),
			rs.getString("navn"),
			rs.getString("bygg_navn"),
			rs.getString("kommune_navn"),
			rs.getString("adressetekst"),
			rs.getString("postnummer"),
			rs.getString("poststed"),
			rs.getString("lokaletype_navn"),
			rs.getObject("lat", Double.class),
			rs.getObject("lon", Double.class),
			rs.getObject("avstand", Double.class),
			rs.getString("booking_url"),
			rs.getString("bilde_url")));
	}

	// Ett kort per bygg med minst én ressurs som traff. Ressurser uten bygg er
	// ikke med her, men finnes i sokRessurser.
	public SokeResultat<ByggSokTreff> sokBygg(RessursSokParametre p)
	{
		Treff t = treff(p);
		String sql = t.sql() + """

			SELECT bygg_id, bygg_navn, bydel_navn, kommune_navn, adressetekst, postnummer, poststed,
			       lat, lon, bygg_booking_url, bygg_bilde_url,
			       count(*)     AS antall_ressurser,
			       max(rang)    AS rang,
			       min(avstand) AS avstand,
			       count(*) OVER () AS totalt
			  FROM treff
			 WHERE bygg_id IS NOT NULL
			 GROUP BY bygg_id, bygg_navn, bydel_navn, kommune_navn, adressetekst, postnummer,
			          poststed, lat, lon, bygg_booking_url, bygg_bilde_url
			 ORDER BY\s""" + switch (p.sorter())
			{
				case "relevans" -> "rang DESC, bygg_navn";
				case "avstand" -> "avstand, bygg_navn";
				default -> "bygg_navn";
			} + ", bygg_id LIMIT :limit OFFSET :offset";

		return kjor(sql, t, p, rs -> new ByggSokTreff(
			rs.getLong("bygg_id"),
			rs.getString("bygg_navn"),
			rs.getString("bydel_navn"),
			rs.getString("kommune_navn"),
			rs.getString("adressetekst"),
			rs.getString("postnummer"),
			rs.getString("poststed"),
			rs.getObject("lat", Double.class),
			rs.getObject("lon", Double.class),
			rs.getObject("avstand", Double.class),
			rs.getInt("antall_ressurser"),
			rs.getString("bygg_booking_url"),
			rs.getString("bygg_bilde_url")));
	}

	// Valgene til filterpanelet. Aktiviteter og fasiliteter hentes fra
	// oppslagstabellene (id og navn), men bare de som er koblet til en ressurs
	// i viewet. Alle aktiviteter er med (flatt, ingen hierarki).
	public SokFiltre hentFiltre()
	{
		return new SokFiltre(hentKommuner(), hentLokaletyper(), hentAktiviteter(), hentFasiliteter());
	}

	public  List<KommuneFilter> hentKommuner(){
		return kommuneFilter("""
				SELECT DISTINCT kommunenr, kommune_navn AS navn
				  FROM v_ressurs_sok
				 ORDER BY navn""");
	}

	public List<FilterValg> hentAktiviteter(){
		return filterValg("""
				SELECT a.id, a.navn
				  FROM aktivitet a
				 WHERE EXISTS (SELECT 1 FROM v_ressurs_sok v WHERE v.aktivitet_ids @> ARRAY[a.id])
				 ORDER BY a.navn""");
	}

	public List<FilterValg> hentLokaletyper(){
		return filterValg("""
				SELECT DISTINCT lokaletype_id AS id, lokaletype_navn AS navn
				  FROM v_ressurs_sok
				 WHERE lokaletype_id IS NOT NULL
				 ORDER BY navn""");
	}

	public List<FilterValg> hentFasiliteter(){
		return filterValg("""
				SELECT f.id, f.navn
				  FROM fasilitet f
				 WHERE EXISTS (SELECT 1 FROM v_ressurs_sok v WHERE v.fasilitet_ids @> ARRAY[f.id])
				 ORDER BY f.navn""");
	}

	// Felles for begge søkene: en CTE som filtrerer viewet og regner ut
	// rangering og avstand per ressurs. Ett if-blokk per filter, så et nytt
	// filter (f.eks. bydel) er én blokk til.
	private record Treff(String sql, Map<String, Object> params)
	{
	}

	private static Treff treff(RessursSokParametre p)
	{
		var where = new StringBuilder("TRUE");
		var params = new HashMap<String, Object>();

		if (p.q() != null)
		{
			// websearch_to_tsquery, ikke to_tsquery: tåler hva som helst av
			// brukerinput uten å kaste syntaksfeil. LIKE-delen gir substreng-
			// treff ("ng" -> "Ungdomshus") som tsvector ikke kan.
			where.append(" AND (sokedokument @@ websearch_to_tsquery('norwegian', :q)")
				.append(" OR navn_sok LIKE :qLike ESCAPE '\\')");
			params.put("q", p.q());
			params.put("qLike", "%" + escapeLike(p.q().toLowerCase(Locale.ROOT)) + "%");
		}
		if (!p.kommune().isEmpty())
		{
			where.append(" AND kommunenr IN (:kommune)");
			params.put("kommune", p.kommune());
		}
		if (!p.lokaletype().isEmpty())
		{
			where.append(" AND lokaletype_id IN (:lokaletype)");
			params.put("lokaletype", p.lokaletype());
		}
		if (!p.aktivitet().isEmpty())
		{
			// &&: ressursen har minst én av de valgte aktivitetene (ELLER).
			where.append(" AND aktivitet_ids && ARRAY[:aktivitet]::bigint[]");
			params.put("aktivitet", p.aktivitet());
		}
		if (!p.fasilitet().isEmpty())
		{
			// @>: ressursen har alle de valgte fasilitetene (OG). Bytt til &&
			// hvis produktet heller vil ha ELLER.
			where.append(" AND fasilitet_ids @> ARRAY[:fasilitet]::bigint[]");
			params.put("fasilitet", p.fasilitet());
		}
		if (p.harNarhet())
		{
			where.append(" AND ST_DWithin(posisjon, ").append(PUNKT).append(", :radius)");
			params.put("lat", p.lat());
			params.put("lon", p.lon());
			params.put("radius", p.radiusMeter());
		}

		String rang = p.q() != null
			? "ts_rank_cd(sokedokument, websearch_to_tsquery('norwegian', :q))"
			: "0::real";
		String avstand = p.harNarhet()
			? "ST_Distance(posisjon, " + PUNKT + ")"
			: "NULL::double precision";

		String sql = "WITH treff AS (SELECT v.*, " + rang + " AS rang, " + avstand + " AS avstand"
			+ " FROM v_ressurs_sok v WHERE " + where + ")";
		return new Treff(sql, params);
	}

	private record Rad<T>(T treff, long totalt)
	{
	}

	// count(*) OVER () gir totalantallet i samme spørring, så paginering
	// ikke krever en ekstra rundtur.
	private <T> SokeResultat<T> kjor(String sql, Treff t, RessursSokParametre p, RadMapper<T> mapper)
	{
		var params = new HashMap<>(t.params());
		params.put("limit", p.storrelse());
		params.put("offset", p.side() * p.storrelse());

		List<Rad<T>> rader = jdbc.sql(sql)
			.params(params)
			.query((rs, i) -> new Rad<>(mapper.map(rs), rs.getLong("totalt")))
			.list();

		return new SokeResultat<>(
			rader.stream().map(Rad::treff).toList(),
			rader.isEmpty() ? 0 : rader.getFirst().totalt(),
			p.side(),
			p.storrelse());
	}

	private List<KommuneFilter> kommuneFilter(String sql)
	{
		return jdbc.sql(sql)
			.query((rs, i) -> new KommuneFilter(rs.getString("kommunenr"), rs.getString("navn")))
			.list();
	}

	private List<FilterValg> filterValg(String sql)
	{
		return jdbc.sql(sql)
			.query((rs, i) -> new FilterValg(rs.getLong("id"), rs.getString("navn")))
			.list();
	}

	@FunctionalInterface
	private interface RadMapper<T>
	{
		T map(ResultSet rs) throws SQLException;
	}

	// Brukerens % og _ skal være vanlige tegn i LIKE-søket, ikke jokertegn.
	private static String escapeLike(String s)
	{
		return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_");
	}
}
