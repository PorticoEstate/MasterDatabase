package no.aktivkommune.masterdatabase.repository;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

import no.aktivkommune.masterdatabase.dto.Kommune;

@Repository
public class KommuneRepository
{
	// A kommune has at most one booking instance (uniq_kommune_fagsystem_type), so the
	// joins never produce more than one row per kommune.
	private static final String SELECT_KOMMUNE = """
			SELECT k.id, k.kommunenr, k.navn, k.fylkesnavn, fi.base_url AS booking_base_url, fi.aktiv AS booking_aktiv
			  FROM kommune k
			  LEFT JOIN kommune_fagsystem_instans kfi ON kfi.kommune_id = k.id AND kfi.type = 'booking'
			  LEFT JOIN fagsystem_instans fi ON fi.id = kfi.fagsystem_instans_id
			""";

	private final JdbcClient jdbc;

	public KommuneRepository(JdbcClient jdbc)
	{
		this.jdbc = jdbc;
	}

	public List<Kommune> getAll()
	{
		return jdbc.sql(SELECT_KOMMUNE + " ORDER BY k.navn")
			.query(Kommune.class)
			.list();
	}

	public Optional<Kommune> getById(long id)
	{
		return jdbc.sql(SELECT_KOMMUNE + " WHERE k.id = :id")
			.param("id", id)
			.query(Kommune.class)
			.optional();
	}

	public long createKommune(String kommunenr, String navn, String fylkesnavn)
	{
		return jdbc.sql("""
				INSERT INTO kommune (kommunenr, navn, fylkesnavn)
				VALUES (:kommunenr, :navn, :fylkesnavn)
				RETURNING id""")
			.param("kommunenr", kommunenr)
			.param("navn", navn)
			.param("fylkesnavn", fylkesnavn)
			.query(Long.class)
			.single();
	}

	public boolean updateKommune(long id, String kommunenr, String navn, String fylkesnavn)
	{
		int rader = jdbc.sql("""
				UPDATE kommune
				   SET kommunenr = :kommunenr, navn = :navn, fylkesnavn = :fylkesnavn, updated_at = now()
				 WHERE id = :id""")
			.param("id", id)
			.param("kommunenr", kommunenr)
			.param("navn", navn)
			.param("fylkesnavn", fylkesnavn)
			.update();
		return rader > 0;
	}

	public boolean deleteKommune(long id)
	{
		return jdbc.sql("DELETE FROM kommune WHERE id = :id")
			.param("id", id)
			.update() > 0;
	}
}
