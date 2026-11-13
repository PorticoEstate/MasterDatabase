package no.aktivkommune.masterdatabase.dto;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import io.swagger.v3.oas.annotations.media.Schema;

// A job in the etl container's queue, as reported by its job server (etl/jobserver.py).
// The job history lives in the etl container's memory only; synk_avvik and kildeuttrekk
// are the permanent record.
@JsonIgnoreProperties(ignoreUnknown = true)
public record EtlJob(

	@Schema(description = "Job id (UUID)")
	String id,

	@Schema(description = "Job type", example = "gater")
	String type,

	@Schema(description = "Arguments the job was started with, e.g. the kommunenr of a gater job. Empty for all kommuner.")
	List<String> args,

	@Schema(description = "queued, running, ok or failed", example = "ok")
	String status,

	@Schema(description = "When the job was queued (ISO 8601)")
	String queuedAt,

	@Schema(description = "When the job started running; null while queued")
	String startedAt,

	@Schema(description = "When the job finished; null until then")
	String finishedAt,

	@Schema(description = "Short result: completed, failed or crashed; null until the job has finished")
	String message,

	@Schema(description = "The last lines the job logged")
	List<String> output
)
{
}
