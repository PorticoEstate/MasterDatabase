package no.aktivkommune.masterdatabase.repository;

import no.aktivkommune.masterdatabase.entity.Ressurs;
import org.springframework.data.jpa.repository.JpaRepository;

// Spring Data lager implementasjonen ved oppstart. findById, findAll, save osv.
// følger med gratis; egne spørringer legges til her ved behov.
public interface RessursRepository extends JpaRepository<Ressurs, Long>
{
}
