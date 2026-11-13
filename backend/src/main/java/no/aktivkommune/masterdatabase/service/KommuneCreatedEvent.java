package no.aktivkommune.masterdatabase.service;

// Published by KommuneService.create inside its transaction. Listeners that must see the
// committed row (e.g. the ETL fetching streets for it) use @TransactionalEventListener.
public record KommuneCreatedEvent(String kommunenr)
{
}
