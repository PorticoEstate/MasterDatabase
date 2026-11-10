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

	// True if a kommune other than kommuneId is linked to the instance with this kildenokkel.
	// For a kommune that does not exist yet, pass 0.
	public boolean instanceInUseByOther(String kildenokkel, long kommuneId)
	{
		return jdbc.sql("""
				SELECT EXISTS (SELECT 1
				                 FROM kommune_fagsystem_instans kfi
				                 JOIN fagsystem_instans fi ON fi.id = kfi.fagsystem_instans_id
				                WHERE fi.kildenokkel = :kildenokkel
				                  AND kfi.kommune_id <> :kommuneId)""")
			.param("kildenokkel", kildenokkel)
			.param("kommuneId", kommuneId)
			.query(Boolean.class)
			.single();
	}

	// The kildenokkel of the kommune's booking instance, if it has one.
	public Optional<String> getBookingKildenokkel(long kommuneId)
	{
		return jdbc.sql("""
				SELECT fi.kildenokkel
				  FROM kommune_fagsystem_instans kfi
				  JOIN fagsystem_instans fi ON fi.id = kfi.fagsystem_instans_id
				 WHERE kfi.kommune_id = :kommuneId AND kfi.type = 'booking'""")
			.param("kommuneId", kommuneId)
			.query(String.class)
			.optional();
	}

	// Registers the booking instance and links it to the kommune. The instance row is the
	// same one etl/synk.py writes (same kildenokkel); if it exists already it is reused and
	// left as it is (aktiv is never changed here, only by setBookingAktiv). Without both rows
	// etl/kommuner_query.sql does not list the kommune.
	public void registerBookingInstance(long kommuneId, String kildenokkel, String navn, String baseUrl)
	{
		jdbc.sql("""
				INSERT INTO fagsystem_instans (kildenokkel, type, navn, base_url)
				VALUES (:kildenokkel, 'booking', :navn, :baseUrl)
				ON CONFLICT (kildenokkel) DO UPDATE SET base_url = EXCLUDED.base_url""")
			.param("kildenokkel", kildenokkel)
			.param("navn", navn)
			.param("baseUrl", baseUrl)
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

	// Sets aktiv on the kommune's booking instance. False if the kommune has none.
	public boolean setBookingAktiv(long kommuneId, boolean aktiv)
	{
		return jdbc.sql("""
				UPDATE fagsystem_instans
				   SET aktiv = :aktiv
				 WHERE id = (SELECT kfi.fagsystem_instans_id
				               FROM kommune_fagsystem_instans kfi
				              WHERE kfi.kommune_id = :kommuneId AND kfi.type = 'booking')""")
			.param("aktiv", aktiv)
			.param("kommuneId", kommuneId)
			.update() > 0;
	}

	// Ids of the instances linked to the kommune. Read before the kommune is deleted.
	public List<Long> getInstanceIds(long kommuneId)
	{
		return jdbc.sql("SELECT fagsystem_instans_id FROM kommune_fagsystem_instans WHERE kommune_id = :kommuneId")
			.param("kommuneId", kommuneId)
			.query(Long.class)
			.list();
	}

	// Deletes the given instances unless some kommune is still linked to them.
	public void deleteUnusedInstances(List<Long> instanceIds)
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
