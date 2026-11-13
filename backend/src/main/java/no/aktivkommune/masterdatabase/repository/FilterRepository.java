package no.aktivkommune.masterdatabase.repository;

import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import no.aktivkommune.masterdatabase.dto.FilterValg;
import no.aktivkommune.masterdatabase.dto.KommuneFilter;

@Repository
public class FilterRepository {
private final JdbcClient jdbc;

public FilterRepository ( JdbcClient jdbc){
	this.jdbc = jdbc;

}

	//Kommuner som inneholder ressurser
		public  List<KommuneFilter> hentKommuner(){
		return jdbc.sql("""
				SELECT DISTINCT kommunenr, kommune_navn AS navn
				  FROM v_ressurs_sok
				 ORDER BY navn""")
				 .query(KommuneFilter.class)
				 .list();
	}

	//Aktivitet, lokaletype og fasilitet hentes direkte fra sine tabeller.
	// Hele kodeverket fra tabellen, også verdier uten ressurser
	// Inneholder både foreldre og barn
		public List<FilterValg> hentAktiviteter(){
		return jdbc.sql("""
			SELECT id, navn, parent_id
			FROM aktivitet
			 ORDER BY parent_id NULLS FIRST, navn """)
			.query(FilterValg.class)
			.list();
	}

		public List<FilterValg> hentLokaletyper(){
		return jdbc.sql("""
			SELECT id, navn, parent_id
			FROM lokaletype
			 ORDER BY parent_id NULLS FIRST, navn """)
			.query(FilterValg.class)
			.list();
	}


	public List<FilterValg> hentFasiliteter(){
		return jdbc.sql("""
			SELECT id, navn, parent_id
			FROM fasilitet
			 ORDER BY parent_id NULLS FIRST, navn """)
			.query(FilterValg.class)
			.list();
	}


}
