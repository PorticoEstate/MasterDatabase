package no.aktivkommune.masterdatabase.service;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

// Starts the street fetch (gater job) for a newly created kommune.
//
// Runs only after the create has committed, so the ETL's "SELECT kommunenr FROM kommune"
// sees the new row. A failure here must never fail or undo the create: it is logged and
// the job can be started by hand with POST /masterdb/etl/jobs/gater.
@Component
public class EtlTrigger
{
	private static final Logger log = LoggerFactory.getLogger(EtlTrigger.class);

	private final EtlClient etl;

	public EtlTrigger(EtlClient etl)
	{
		this.etl = etl;
	}

	@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
	public void onKommuneCreated(KommuneCreatedEvent event)
	{
		try
		{
			etl.enqueue("gater", List.of(event.kommunenr()));
			log.info("Queued a gater job for the new kommune {}", event.kommunenr());
		}
		catch (Exception e)
		{
			log.warn("Could not queue a gater job for the new kommune {} ({}). Start it with POST /masterdb/etl/jobs/gater.",
				event.kommunenr(), e.getMessage());
		}
	}
}
