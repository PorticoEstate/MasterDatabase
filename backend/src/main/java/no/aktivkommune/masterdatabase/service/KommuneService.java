package no.aktivkommune.masterdatabase.service;

import java.util.List;
import java.util.Optional;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import no.aktivkommune.masterdatabase.dto.AktivKommuneUrl;
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

	// With a bookingBaseUrl the booking system is registered in the same transaction, so the
	// kommune is either created ready to be synced or not created at all.
	@Transactional
	public Kommune create(String kommunenr, String navn, String fylkesnavn, String bookingBaseUrl)
	{
		String slug = null;
		if (bookingBaseUrl != null)
		{
			slug = AktivKommuneUrl.slugOf(bookingBaseUrl);
			if (slug == null)
			{
				throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
					"bookingBaseUrl must be https://<name>.aktiv-kommune.no");
			}
			// The ETL list is keyed on the subdomain, so two kommuner cannot share one.
			if (repository.instanceInUseByOther(AktivKommuneUrl.kildenokkelOf(slug), 0))
			{
				throw new ResponseStatusException(HttpStatus.CONFLICT,
					"bookingBaseUrl " + AktivKommuneUrl.baseUrlOf(slug) + " is already registered for another kommune");
			}
		}

		long id;
		try
		{
			id = repository.createKommune(kommunenr, navn.strip(), fylkesnavn);
		}
		catch (DuplicateKeyException e)
		{
			throw new ResponseStatusException(HttpStatus.CONFLICT, "kommunenr " + kommunenr + " already exists");
		}

		if (slug != null)
		{
			repository.registerBookingInstance(id, AktivKommuneUrl.kildenokkelOf(slug),
				"Aktiv kommune " + navn.strip(), AktivKommuneUrl.baseUrlOf(slug));
		}
		return repository.getById(id).orElseThrow();
	}

	// kommunenr, navn and fylkesnavn are replaced. The booking system is only touched when a
	// bookingBaseUrl is given: it is set if the kommune has none, and repeating the registered
	// URL changes nothing. A different URL is rejected, because the kommune's buildings and
	// resources are tied to the instance they were loaded from. An update never removes the
	// booking system. Any error rolls the whole update back.
	@Transactional
	public void update(long id, String kommunenr, String navn, String fylkesnavn, String bookingBaseUrl)
	{
		String slug = null;
		if (bookingBaseUrl != null)
		{
			slug = AktivKommuneUrl.slugOf(bookingBaseUrl);
			if (slug == null)
			{
				throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
					"bookingBaseUrl must be https://<name>.aktiv-kommune.no");
			}
		}

		boolean updated;
		try
		{
			updated = repository.updateKommune(id, kommunenr, navn.strip(), fylkesnavn);
		}
		catch (DuplicateKeyException e)
		{
			// kommunenr is editable, so it can collide with another kommune's.
			throw new ResponseStatusException(HttpStatus.CONFLICT, "kommunenr " + kommunenr + " already exists");
		}
		if (!updated)
		{
			throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No kommune with id " + id);
		}

		if (slug != null)
		{
			String kildenokkel = AktivKommuneUrl.kildenokkelOf(slug);
			Optional<String> current = repository.getBookingKildenokkel(id);
			if (current.isPresent() && !current.get().equals(kildenokkel))
			{
				throw new ResponseStatusException(HttpStatus.CONFLICT,
					"The kommune already has another booking system (" + current.get()
						+ "); changing it is not supported");
			}
			if (repository.instanceInUseByOther(kildenokkel, id))
			{
				throw new ResponseStatusException(HttpStatus.CONFLICT,
					"bookingBaseUrl " + AktivKommuneUrl.baseUrlOf(slug) + " is already registered for another kommune");
			}
			repository.registerBookingInstance(id, kildenokkel,
				"Aktiv kommune " + navn.strip(), AktivKommuneUrl.baseUrlOf(slug));
		}
	}

	// Also removes the kommune's booking system if no other kommune uses it, so the same URL
	// can be registered again later.
	@Transactional
	public void delete(long id)
	{
		List<Long> instanceIds = repository.getInstanceIds(id);
		if (!repository.deleteKommune(id))
		{
			throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No kommune with id " + id);
		}
		repository.deleteUnusedInstances(instanceIds);
	}
}
