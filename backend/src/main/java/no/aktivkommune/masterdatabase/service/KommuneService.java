package no.aktivkommune.masterdatabase.service;

import java.util.List;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import no.aktivkommune.masterdatabase.dto.AktivKommuneUrl;
import no.aktivkommune.masterdatabase.dto.Kommune;
import no.aktivkommune.masterdatabase.repository.FagsystemInstansRepository;
import no.aktivkommune.masterdatabase.repository.KommuneRepository;

@Service
public class KommuneService
{
	private static final String BOOKING = "booking";

	private final KommuneRepository repository;
	private final FagsystemInstansRepository instanser;

	public KommuneService(KommuneRepository repository, FagsystemInstansRepository instanser)
	{
		this.repository = repository;
		this.instanser = instanser;
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

	// The booking system is registered in the same transaction, so the kommune is either
	// created ready to be synced or not created at all.
	@Transactional
	public Kommune create(String kommunenr, String navn, String fylkesnavn, String bookingBaseUrl, boolean active)
	{
		String slug = AktivKommuneUrl.slugOf(bookingBaseUrl);
		if (slug == null)
		{
			throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
				"bookingBaseUrl is required and must be https://<name>.aktiv-kommune.no");
		}
		// The ETL list is keyed on the subdomain, so two kommuner cannot share one.
		if (instanser.isRegistered(AktivKommuneUrl.kildenokkelOf(slug)))
		{
			throw new ResponseStatusException(HttpStatus.CONFLICT,
				"bookingBaseUrl " + AktivKommuneUrl.baseUrlOf(slug) + " is already registered for another kommune");
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
		instanser.register(
			id,
			BOOKING,
			AktivKommuneUrl.kildenokkelOf(slug),
			"Aktiv kommune " + navn.strip(), AktivKommuneUrl.baseUrlOf(slug),
			active);
		return repository.getById(id).orElseThrow();
	}

	// kommunenr, navn and fylkesnavn are replaced. The booking system is not touched here:
	// it is registered when the kommune is created, and its URL is tied to the buildings and
	// resources loaded from it.
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
			// kommunenr is editable, so it can collide with another kommune's.
			throw new ResponseStatusException(HttpStatus.CONFLICT, "kommunenr " + kommunenr + " already exists");
		}
		if (!updated)
		{
			throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No kommune with id " + id);
		}
	}

	// Includes or excludes the kommune's booking system in the nightly sync. Idempotent.
	@Transactional
	public Kommune setBookingAktiv(long id, boolean aktiv)
	{
		getById(id);  // 404 if the kommune does not exist
		if (!instanser.setAktivStatus(id, BOOKING, aktiv))
		{
			throw new ResponseStatusException(HttpStatus.CONFLICT, "The kommune has no booking system");
		}
		return getById(id);
	}

	// Also removes the kommune's booking system if no other kommune uses it, so the same URL
	// can be registered again later.
	@Transactional
	public void delete(long id)
	{
		List<Long> instanceIds = instanser.idsFor(id);
		if (!repository.deleteKommune(id))
		{
			throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No kommune with id " + id);
		}
		instanser.deleteUnused(instanceIds);
	}
}
