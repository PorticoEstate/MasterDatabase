package no.aktivkommune.masterdatabase.controller;

import java.util.List;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import no.aktivkommune.masterdatabase.dto.EtlJob;
import no.aktivkommune.masterdatabase.dto.EtlJobAccepted;
import no.aktivkommune.masterdatabase.dto.EtlJobRequest;
import no.aktivkommune.masterdatabase.service.EtlClient;

// Starts and follows ETL jobs in the etl container. Every endpoint requires the
// X-API-KEY header (checked by ApiKeyFilter; this path is not in its OPEN_PATHS).
@RestController
@RequestMapping("/masterdb/etl/jobs")
@Tag(name = "ETL jobs", description = "Start and follow ETL jobs (sync, geocode, gater). Requires an API key.")
@SecurityRequirement(name = "apiKey")
@ApiResponse(responseCode = "401", description = "Missing or invalid API key", content = @Content)
@ApiResponse(responseCode = "502", description = "Unexpected answer from the ETL service", content = @Content)
@ApiResponse(responseCode = "503", description = "The ETL service is not available", content = @Content)
public class EtlController
{
	private final EtlClient etl;

	public EtlController(EtlClient etl)
	{
		this.etl = etl;
	}

	@Operation(summary = "Queue a sync job",
			description = "Runs the recurring sync for all kommuner now. Queued, one job at a time; "
					+ "an identical waiting job is reused (deduplicated=true). Follow it with GET /masterdb/etl/jobs/{id}.")
	@PostMapping("/sync")
	@ResponseStatus(HttpStatus.ACCEPTED)
	public EtlJobAccepted enqueueSync()
	{
		return etl.enqueue("sync", List.of());
	}

	@Operation(summary = "Queue a geocode job",
			description = "Runs Matrikkel geocoding for buildings without a position. Queued and deduplicated like sync.")
	@PostMapping("/geocode")
	@ResponseStatus(HttpStatus.ACCEPTED)
	public EtlJobAccepted enqueueGeocode()
	{
		return etl.enqueue("geocode", List.of());
	}

	@Operation(summary = "Queue a gater job",
			description = "Fetches streets (gate) from Matrikkel. A body {\"kommunenr\": [...]} limits it to those "
					+ "kommuner; without a body every kommune is fetched. Queued and deduplicated like sync.")
	@ApiResponse(responseCode = "400", description = "Invalid body", content = @Content)
	@PostMapping("/gater")
	@ResponseStatus(HttpStatus.ACCEPTED)
	public EtlJobAccepted enqueueGater(@Valid @RequestBody(required = false) EtlJobRequest request)
	{
		return etl.enqueue("gater", request == null ? List.of() : request.kommunenr());
	}

	@Operation(summary = "List recent ETL jobs",
			description = "The last jobs the etl container remembers, newest first. The history is lost when the container restarts.")
	@GetMapping
	public List<EtlJob> list()
	{
		return etl.list();
	}

	@Operation(summary = "Get an ETL job by id")
	@ApiResponse(responseCode = "400", description = "The id is not a UUID", content = @Content)
	@ApiResponse(responseCode = "404", description = "No such job (it may have been forgotten after a restart)", content = @Content)
	@GetMapping("/{id}")
	public EtlJob get(@PathVariable UUID id)
	{
		return etl.get(id.toString());
	}
}
