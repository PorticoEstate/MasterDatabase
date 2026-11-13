package no.aktivkommune.masterdatabase.controller;

import java.util.List;
import java.util.Set;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
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
public class EtlController
{
	private static final Set<String> TYPES = Set.of("sync", "geocode", "gater");

	private final EtlClient etl;

	public EtlController(EtlClient etl)
	{
		this.etl = etl;
	}

	@Operation(summary = "Queue an ETL job",
			description = "type is sync, geocode or gater. The job is queued in the etl container, which runs one "
					+ "job at a time, and the call returns at once with the job id. An identical job that is "
					+ "still waiting is reused (deduplicated=true). For gater, a body {\"kommunenr\": [...]} limits it to "
					+ "those kommuner; without a body every kommune in the database is fetched. Follow the job with "
					+ "GET /masterdb/etl/jobs/{id}.")
	@ApiResponses({
		@ApiResponse(responseCode = "400", description = "Invalid body, or a body on a job type that takes none", content = @Content),
		@ApiResponse(responseCode = "404", description = "Unknown job type", content = @Content),
		@ApiResponse(responseCode = "502", description = "Unexpected answer from the ETL service", content = @Content),
		@ApiResponse(responseCode = "503", description = "The ETL service is not available", content = @Content)
	})
	@PostMapping("/{type}")
	@ResponseStatus(HttpStatus.ACCEPTED)
	public EtlJobAccepted enqueue(@PathVariable String type, @Valid @RequestBody(required = false) EtlJobRequest request)
	{
		if (!TYPES.contains(type))
		{
			throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Unknown job type: " + type);
		}
		if (request != null && !type.equals("gater"))
		{
			throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Only gater takes a body");
		}
		return etl.enqueue(type, request == null ? List.of() : request.kommunenr());
	}

	@Operation(summary = "List recent ETL jobs",
			description = "The last jobs the etl container remembers, newest first. The history is lost when the container restarts.")
	@ApiResponses({
		@ApiResponse(responseCode = "502", description = "Unexpected answer from the ETL service", content = @Content),
		@ApiResponse(responseCode = "503", description = "The ETL service is not available", content = @Content)
	})
	@GetMapping
	public List<EtlJob> list()
	{
		return etl.list();
	}

	@Operation(summary = "Get an ETL job by id")
	@ApiResponses({
		@ApiResponse(responseCode = "400", description = "The id is not a UUID", content = @Content),
		@ApiResponse(responseCode = "404", description = "No such job (it may have been forgotten after a restart)", content = @Content),
		@ApiResponse(responseCode = "502", description = "Unexpected answer from the ETL service", content = @Content),
		@ApiResponse(responseCode = "503", description = "The ETL service is not available", content = @Content)
	})
	@GetMapping("/{id}")
	public EtlJob get(@PathVariable UUID id)
	{
		return etl.get(id.toString());
	}
}
