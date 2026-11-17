package no.aktivkommune.masterdatabase.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import io.swagger.v3.oas.annotations.media.Schema;

// The etl container's answer when a job is queued.
@JsonIgnoreProperties(ignoreUnknown = true)
public record EtlJobAccepted(

	@Schema(description = "Job id (UUID). Use it with GET /masterdb/etl/jobs/{id}.")
	String id,

	@Schema(description = "Job type", example = "gater")
	String type,

	@Schema(description = "queued or running", example = "queued")
	String status,

	@Schema(description = "Number of jobs ahead of this one, including the one running", example = "0")
	int queuePosition,

	@Schema(description = "True if an identical job was already waiting in the queue; then this is that job and nothing new was added")
	boolean deduplicated
)
{
}
