package no.aktivkommune.masterdatabase.repository;

import no.aktivkommune.masterdatabase.dto.Bygg;
import no.aktivkommune.masterdatabase.dto.RessursSokParametere;
import no.aktivkommune.masterdatabase.dto.Ressurs;
import no.aktivkommune.masterdatabase.dto.ResultatSide;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;
import java.util.HashMap;
import java.util.List;
import java.util.ArrayList;
import java.util.Map;

// All SQL for søket, mot v_ressurs_sok.
// Søket bruker JdbcClient med ren SQL fordi det er Postgres-spesifikt: fulltekst
// (tsvector/@@), PostGIS (ST_DWithin, ST_Distance) og array-operatoren &&
// Når søket feiler eller er tregt, kan spørringen under limes rett inn i psql med EXPLAIN ANALYZE.

// Brukerinput går alltid som navngitte parametre (:fritekst, :kommune, ...), aldri
// inn i SQL-strengen.--hindrer SQL-injeksjon

@Repository
public class RessursSokRepository {
	// Lager et PostGis-punkt. SRID 4326 gjør det om til GPS-koordinater i grader.
	private static final String SOKEPUNKT = "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography";

	private final JdbcClient jdbc;

	public RessursSokRepository(JdbcClient jdbc) {
		this.jdbc = jdbc;
	}

	// Tar imot det brukeren har valgt (p, allerede normalisert av servicen) og returnerer én side med ressurser
	public ResultatSide<Ressurs> sokRessurser(RessursSokParametere p) {

		// lagFiltrertSqlSok bygger WITH-delen (filter, rang og avstand) som SQL-tekst + parametre
		SokeFilter sokeFilterSql = lagFiltrertSqlSok(p);

		// hele spørringen som tekst (WITH-delen + SELECT/ORDER BY). Parameterverdiene
		// ligger i sokeFilterSql.params
		String sql = sokeFilterSql.sql() +
				"""
						SELECT ressurs_id,
							   navn,
							   bygg_navn,
							   kommune_navn,
							   adressetekst, postnummer, poststed,
						       lokaletype_navn,
							   lat, lon, avstand,
							   booking_url,
						       count(*) OVER () AS totalt
						FROM treff
						ORDER BY\s""" + switch (p.sorter()) {
					case "relevans" -> "rang DESC, navn";
					case "avstand" -> "avstand, navn";
					default -> "navn";
				} + ", ressurs_id LIMIT :limit OFFSET :offset";

		return hentSide(sql, sokeFilterSql.params, p, (rs, radnr) -> new Ressurs(
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
				rs.getString("booking_url")));
	}

	// Ett kort per bygg med minst én ressurs som traff.
	public ResultatSide<Bygg> sokBygg(RessursSokParametere p) {
		SokeFilter sokeFilterSql = lagFiltrertSqlSok(p);
		String sql = sokeFilterSql.sql() + """

				SELECT bygg_id,
					   bygg_navn,
					   bydel_navn,
					   kommune_navn,
					   adressetekst, postnummer, poststed,
				       lat, lon,
					   bygg_booking_url,
				       count(*)     AS antall_ressurser,
				       max(rang)    AS rang,
				       min(avstand) AS avstand,
				       count(*) OVER () AS totalt
				FROM treff
				WHERE bygg_id IS NOT NULL
				GROUP BY bygg_id, bygg_navn, bydel_navn, kommune_navn, adressetekst, postnummer,
				          poststed, lat, lon, bygg_booking_url
				ORDER BY\s""" + switch (p.sorter()) {
			case "relevans" -> "rang DESC, bygg_navn";
			case "avstand" -> "avstand, bygg_navn";
			default -> "bygg_navn";
		} + ", bygg_id LIMIT :limit OFFSET :offset";

		return hentSide(sql, sokeFilterSql.params, p, (rs, radnr) -> new Bygg(
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
				rs.getString("bygg_booking_url")));
	}

	private record SokeFilter(String sql, Map<String, Object> params) {
	}

	// Bygger WITH-delen (CTE-en «treff») av søket fra de normaliserte parametrene fra servicen.
	private static SokeFilter lagFiltrertSqlSok(RessursSokParametere p) {
		var betingelser = new ArrayList<String>(List.of("TRUE"));
		var params = new HashMap<String, Object>();

		boolean harFritekst = p.fritekst() != null;
		if (harFritekst) {
			// websearch_to_tsquery tåler hva som helst av brukerinput uten å kaste syntaksfeil.
			betingelser.add("(sokedokument @@ websearch_to_tsquery('norwegian', :fritekst)"
					+ " OR strpos(navn_sok, lower(:fritekst)) > 0)");
			params.put("fritekst", p.fritekst());
		}

		if (!p.kommune().isEmpty()) {
			betingelser.add("kommunenr IN (:kommune)");
			params.put("kommune", p.kommune());
		}

		// Lokaletype, aktivitet og fasilitet: ELLER mellom valgene.
		if (!p.lokaletype().isEmpty()) {
			betingelser.add("""
					lokaletype_id IN(
					SELECT underlokaletype_id
					FROM mv_lokaletype_hierarki
					WHERE lokaletype_id IN (:lokaletype))""");
			params.put("lokaletype", p.lokaletype());
		}

		if (!p.aktivitet().isEmpty()) {
			betingelser.add("""
					aktivitet_ids && ARRAY(
					SELECT underaktivitet_id
					FROM mv_aktivitet_hierarki
					WHERE aktivitet_id IN (:aktivitet))""");
			params.put("aktivitet", p.aktivitet());
		}

		if (!p.fasilitet().isEmpty()) {
			betingelser.add("""
					fasilitet_ids && ARRAY(
					SELECT underfasilitet_id
					FROM mv_fasilitet_hierarki
					WHERE fasilitet_id IN (:fasilitet))""");
			params.put("fasilitet", p.fasilitet());
		}

		if (p.harNarhet()) {
			betingelser.add("ST_DWithin(posisjon, " + SOKEPUNKT + ", :radius)");
			params.put("lat", p.lat());
			params.put("lon", p.lon());
			params.put("radius", p.radiusMeter());
		}

		// Kolonnene rang og avstand beregnes i WITH-delen, slik at resultatet kan sorteres
		String rang = harFritekst
				? "ts_rank_cd(sokedokument, websearch_to_tsquery('norwegian', :fritekst))"
				: "0::real";

		// avstand i meter fra søkepunktet (NULL uten nærhetssøk).
		String avstand = p.harNarhet()
				? "ST_Distance(posisjon, " + SOKEPUNKT + ")"
				: "NULL::double precision";

		String where = String.join(" AND ", betingelser);

		String sql = """
				WITH treff AS (
				SELECT v.*, %s AS rang, %s AS avstand
				FROM v_ressurs_sok v WHERE %s)
					""".formatted(rang, avstand, where);

		return new SokeFilter(sql, params);
	}

	private record Rad<T>(T treff, long totalt) {
	}

	// count(*) OVER () gir totalantallet i samme spørring, så paginering ikke krever en ekstra rundtur.
	private <T> ResultatSide<T> hentSide(String sql, Map<String, Object> plassholder, RessursSokParametere p,
			RowMapper<T> radmapper) {
		long offset = (long) p.side() * p.storrelse();

		// kjører spørringen
		List<Rad<T>> rader = jdbc.sql(sql)
				.params(plassholder)
				.param("limit", p.storrelse())
				.param("offset", offset)
				.query((rs, radnr) -> new Rad<>(radmapper.mapRow(rs, radnr), rs.getLong("totalt")))
				.list();

		return new ResultatSide<>(
				rader.stream().map(Rad::treff).toList(),
				rader.isEmpty() ? 0 : rader.getFirst().totalt(),
				p.side(),
				p.storrelse());
	}

}
