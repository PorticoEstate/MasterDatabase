package no.aktivkommune.masterdatabase.service;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import no.aktivkommune.masterdatabase.repository.AktivitetRepository;

@Service
public class AktivitetService
{
	private final AktivitetRepository repository;

	public AktivitetService(AktivitetRepository repository)
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
			throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "An aktivitet cannot be its own parent");
		}

		boolean updated;
		try
		{
			updated = repository.update(id, navn.strip(), parentId);
		}
		catch (DuplicateKeyException e)
		{
			throw new ResponseStatusException(HttpStatus.CONFLICT, "An aktivitet named " + navn.strip() + " already exists");
		}
		catch (DataIntegrityViolationException e)
		{
			// The only other constraint an update can break is the foreign key on parent_id.
			throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "No aktivitet with id " + parentId + " to use as parent");
		}
		if (!updated)
		{
			throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No aktivitet with id " + id);
		}
	}

	// A parent cannot be deleted: its children would silently lose their place in
	// the hierarchy (ON DELETE SET NULL). Links from resources are removed with the
	// aktivitet (ON DELETE CASCADE).
	@Transactional
	public void delete(long id)
	{
		if (repository.hasChildren(id))
		{
			throw new ResponseStatusException(HttpStatus.CONFLICT,
				"Aktivitet " + id + " is the parent of other aktiviteter and cannot be deleted");
		}
		if (!repository.delete(id))
		{
			throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No aktivitet with id " + id);
		}
	}
}
