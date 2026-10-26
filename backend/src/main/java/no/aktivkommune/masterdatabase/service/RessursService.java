package no.aktivkommune.masterdatabase.service;

import no.aktivkommune.masterdatabase.dto.RessursDto;
import no.aktivkommune.masterdatabase.entity.Lokaletype;
import no.aktivkommune.masterdatabase.entity.Ressurs;
import no.aktivkommune.masterdatabase.repository.RessursRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Optional;

@Service
public class RessursService
{
	private final RessursRepository ressursRepository;

	public RessursService(RessursRepository ressursRepository)
	{
		this.ressursRepository = ressursRepository;
	}

	// @Transactional holder sesjonen åpen mens vi mapper til DTO, slik at
	// lazy-assosiasjonen lokaletype kan lastes. DTO-en som forlater metoden er
	// ren data og trenger ikke databasen lenger.
	@Transactional(readOnly = true)
	public Optional<RessursDto> hent(Long id)
	{
		return ressursRepository.findById(id).map(RessursService::tilDto);
	}

	private static RessursDto tilDto(Ressurs r)
	{
		Lokaletype lokaletype = r.getLokaletype();
		return new RessursDto(
			r.getId(),
			r.getFagsystemInstansId(),
			r.getEksternId(),
			r.getKommuneId(),
			r.getBygningId(),
			r.getNavn(),
			lokaletype != null ? lokaletype.getId() : null,
			lokaletype != null ? lokaletype.getKode() : null,
			lokaletype != null ? lokaletype.getNavn() : null,
			r.getKapasitet(),
			r.getArealM2(),
			r.getBeskrivelse(),
			r.getAktiv(),
			r.getBookbar(),
			r.getSistOppdatert(),
			r.getCreatedAt(),
			r.getUpdatedAt());
	}
}
