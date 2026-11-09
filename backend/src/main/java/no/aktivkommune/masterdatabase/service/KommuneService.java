package no.aktivkommune.masterdatabase.service;

import java.util.List;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import no.aktivkommune.masterdatabase.dto.Kommune;
import no.aktivkommune.masterdatabase.repository.KommuneRepository;

@Service
public class KommuneService
{
	private final KommuneRepository repository;

	public KommuneService(KommuneRepository repository)
	{
		this.repository = repository;
	}

	@Transactional(readOnly = true)
	public List<Kommune> getAll()
	{
		return repository.getAll();
	}

	@Transactional(readOnly = true)
	public Kommune getById(long id)
	{
		return repository.getById(id)
			.orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "No kommune with id " + id));
	}

	@Transactional
	public Kommune create(String kommunenr, String navn, String fylkesnavn)
	{
		try
		{
			long id = repository.createKommune(kommunenr, navn.strip(), fylkesnavn);
			return repository.getById(id).orElseThrow();
		}
		catch (DuplicateKeyException e)
		{
			throw new ResponseStatusException(HttpStatus.CONFLICT, "kommunenr " + kommunenr + " already exists");
		}
	}

	@Transactional
	public void update(long id, String kommunenr, String navn, String fylkesnavn)
	{
		boolean updated;
		try
		{
			updated = repository.updateKommune(id, kommunenr, navn.strip(), fylkesnavn);
		}
		catch (DuplicateKeyException e)
		{
			// kommunenr is editable now, so it can collide with another kommune's.
			throw new ResponseStatusException(HttpStatus.CONFLICT, "kommunenr " + kommunenr + " already exists");
		}
		if (!updated)
		{
			throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No kommune with id " + id);
		}
	}

	@Transactional
	public void delete(long id)
	{
		if (!repository.deleteKommune(id))
		{
			throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No kommune with id " + id);
		}
	}
}
