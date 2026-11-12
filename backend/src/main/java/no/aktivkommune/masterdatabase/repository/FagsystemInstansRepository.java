package no.aktivkommune.masterdatabase.repository;

import java.util.List;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

// fagsystem_instans and its link to kommuner (kommune_fagsystem_instans). The same rows are
// written by etl/synk.py and etl/last_inn.py, so kildenokkel is the shared key. A kommune has
// at most one instance per type (uniq_kommune_fagsystem_type).
@Repository
public class FagsystemInstansRepository
{
	private final JdbcClient jdbc;

	public FagsystemInstansRepository(JdbcClient jdbc)
	{
		this.jdbc = jdbc;
	}

	// True if a kommune is already linked to the instance with this kildenokkel.
	public boolean isRegistered(String kildenokkel)
	{
		return jdbc.sql("""
				SELECT EXISTS (SELECT 1
				                 FROM kommune_fagsystem_instans kfi
				                 JOIN fagsystem_instans fi ON fi.id = kfi.fagsystem_instans_id
				                WHERE fi.kildenokkel = :kildenokkel)""")
			.param("kildenokkel", kildenokkel)
			.query(Boolean.class)
			.single();
	}

	// Registers the instance and links it to the kommune. If an instance with this kildenokkel
	// exists already (not expected: the service rejects a URL that is linked to a kommune, so this is only an
	// orphaned instance) it is reused and its base_url and aktiv are set from the arguments.
	// Without both rows etl/kommuner_query.sql does not list the kommune.
	public void register(long kommuneId, String type, String kildenokkel, String navn, String baseUrl, boolean active)
	{
		jdbc.sql("""
				INSERT INTO fagsystem_instans (kildenokkel, type, navn, base_url, aktiv)
				VALUES (:kildenokkel, :type, :navn, :baseUrl, :active)
				ON CONFLICT (kildenokkel) DO UPDATE SET base_url = EXCLUDED.base_url, aktiv = EXCLUDED.aktiv""")
			.param("kildenokkel", kildenokkel)
			.param("type", type)
			.param("navn", navn)
			.param("baseUrl", baseUrl)
			.param("active", active)
			.update();

		jdbc.sql("""
				INSERT INTO kommune_fagsystem_instans (kommune_id, fagsystem_instans_id, type)
				SELECT CAST(:kommuneId AS BIGINT), fi.id, fi.type
				  FROM fagsystem_instans fi
				 WHERE fi.kildenokkel = :kildenokkel
				ON CONFLICT (kommune_id, fagsystem_instans_id) DO NOTHING""")
			.param("kommuneId", kommuneId)
			.param("kildenokkel", kildenokkel)
			.update();
	}

	// Sets aktiv on the kommune's instance of this type. False if the kommune has none.
	public boolean setAktivStatus(long kommuneId, String type, boolean aktiv)
	{
		return jdbc.sql("""
				UPDATE fagsystem_instans
				   SET aktiv = :aktiv
				 WHERE id = (SELECT kfi.fagsystem_instans_id
				               FROM kommune_fagsystem_instans kfi
				              WHERE kfi.kommune_id = :kommuneId AND kfi.type = :type)""")
			.param("aktiv", aktiv)
			.param("kommuneId", kommuneId)
			.param("type", type)
			.update() > 0;
	}

	// Ids of the instances linked to the kommune. Read before the kommune is deleted.
	public List<Long> idsFor(long kommuneId)
	{
		return jdbc.sql("SELECT fagsystem_instans_id FROM kommune_fagsystem_instans WHERE kommune_id = :kommuneId")
			.param("kommuneId", kommuneId)
			.query(Long.class)
			.list();
	}

	// Deletes the given instances unless some kommune is still linked to them.
	public void deleteUnused(List<Long> instanceIds)
	{
		if (instanceIds.isEmpty())
		{
			return;
		}
		jdbc.sql("""
				DELETE FROM fagsystem_instans fi
				 WHERE fi.id IN (:ids)
				   AND NOT EXISTS (SELECT 1 FROM kommune_fagsystem_instans kfi
				                    WHERE kfi.fagsystem_instans_id = fi.id)""")
			.param("ids", instanceIds)
			.update();
	}
}
