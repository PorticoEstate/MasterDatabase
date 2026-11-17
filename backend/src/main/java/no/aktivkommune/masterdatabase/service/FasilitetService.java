package no.aktivkommune.masterdatabase.service;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import no.aktivkommune.masterdatabase.repository.FasilitetRepository;

@Service
public class FasilitetService
{
	private final FasilitetRepository repository;

	public FasilitetService(FasilitetRepository repository)
	{
		this.repository = repository;
	}

	// navn and parent_id are replaced. The id is the one shared with the kommune
	// instances and cannot be changed.
	@Transactional
	public void update(long id, String navn, Long parentId)
	{
		if (parentId != null && parentId == id)
		{
			throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "A fasilitet cannot be its own parent");
		}

		boolean updated;
		try
		{
			updated = repository.update(id, navn.strip(), parentId);
		}
		catch (DuplicateKeyException e)
		{
			throw new ResponseStatusException(HttpStatus.CONFLICT, "A fasilitet named " + navn.strip() + " already exists");
		}
		catch (DataIntegrityViolationException e)
		{
			// The only other constraint an update can break is the foreign key on parent_id.
			throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "No fasilitet with id " + parentId + " to use as parent");
		}
		if (!updated)
		{
			throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No fasilitet with id " + id);
		}
	}

	// A parent cannot be deleted: its children would silently lose their place in
	// the hierarchy (ON DELETE SET NULL). Links from resources are removed with the
	// fasilitet (ON DELETE CASCADE).
	@Transactional
	public void delete(long id)
	{
		if (repository.hasChildren(id))
		{
			throw new ResponseStatusException(HttpStatus.CONFLICT,
				"Fasilitet " + id + " is the parent of other fasiliteter and cannot be deleted");
		}
		if (!repository.delete(id))
		{
			throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No fasilitet with id " + id);
		}
	}
}
