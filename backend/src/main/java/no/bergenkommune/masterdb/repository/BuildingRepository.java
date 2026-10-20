package no.bergenkommune.masterdb.repository;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import no.bergenkommune.masterdb.domain.Building;

@Repository
public class BuildingRepository {

    private final JdbcTemplate jdbcTemplate;

    public BuildingRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    /**
     * Keyset-paginering på id (ikke OFFSET) - stabil selv om rader legges til
     * mellom to sider. "cursor" er id-en til siste rad på forrige side.
     */
    public List<Building> list(String bydelNavn, int limit, Long cursor) {
        StringBuilder sql = new StringBuilder(
            "SELECT id, bygningsnr, navn, bydel_navn, geom_wkt FROM bygning WHERE 1=1 ");
        List<Object> args = new java.util.ArrayList<>();
        if (bydelNavn != null && !bydelNavn.isBlank()) {
            sql.append("AND bydel_navn = ? ");
            args.add(bydelNavn);
        }
        if (cursor != null) {
            sql.append("AND id > ? ");
            args.add(cursor);
        }
        sql.append("ORDER BY id LIMIT ?");
        args.add(limit);

        return jdbcTemplate.query(sql.toString(), args.toArray(), (rs, rowNum) -> new Building(
            rs.getLong("id"),
            rs.getObject("bygningsnr", Long.class),
            rs.getString("navn"),
            rs.getString("bydel_navn"),
            rs.getString("geom_wkt")
        ));
    }
}
