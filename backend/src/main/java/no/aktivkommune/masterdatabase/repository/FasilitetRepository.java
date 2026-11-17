package no.aktivkommune.masterdatabase.repository;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class FasilitetRepository
{
	private final JdbcClient jdbc;

	public FasilitetRepository(JdbcClient jdbc)
	{
		this.jdbc = jdbc;
	}

	public boolean update(long id, String navn, Long parentId)
	{
		int rader = jdbc.sql("""
				UPDATE fasilitet
				   SET navn = :navn, parent_id = :parentId, updated_at = now()
				 WHERE id = :id""")
			.param("id", id)
			.param("navn", navn)
			.param("parentId", parentId)
			.update();
		return rader > 0;
	}

	public boolean hasChildren(long id)
	{
		return jdbc.sql("SELECT EXISTS (SELECT 1 FROM fasilitet WHERE parent_id = :id)")
			.param("id", id)
			.query(Boolean.class)
			.single();
	}

	public boolean delete(long id)
	{
		return jdbc.sql("DELETE FROM fasilitet WHERE id = :id")
			.param("id", id)
			.update() > 0;
	}
}
