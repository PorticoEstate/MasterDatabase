package no.bergenkommune.masterdb.domain;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Speiler kolonnene i tabellen "bygning" (db/schema_kjerne.sql) som er
 * relevante for et read-only API. "bydel_navn" er fritekst i kilden - det
 * finnes ingen bydel_id i databasen i dag.
 */
public record Building(
    @JsonProperty("bygg_id") long byggId,
    @JsonProperty("bygningsnr") Long bygningsnr,
    @JsonProperty("navn") String navn,
    @JsonProperty("bydel_navn") String bydelNavn,
    @JsonProperty("geom_wkt") String geomWkt
) {
}
