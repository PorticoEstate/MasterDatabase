package no.aktivkommune.masterdatabase.repository;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

import no.aktivkommune.masterdatabase.dto.Kommune;

@Repository
public class KommuneRepository
{
	private final JdbcClient jdbc;

	public KommuneRepository(JdbcClient jdbc)
	{
		this.jdbc = jdbc;
	}

	public List<Kommune> getAll()
	{
		return jdbc.sql("""
				SELECT id, kommunenr, navn, fylkesnavn
				  FROM kommune
				 ORDER BY navn""")
			.query(Kommune.class)
			.list();
	}

	public Optional<Kommune> getById(long id)
	{
		return jdbc.sql("""
				SELECT id, kommunenr, navn, fylkesnavn
				  FROM kommune
				 WHERE id = :id""")
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
