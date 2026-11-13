package no.aktivkommune.masterdatabase.dto;

import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

// Optional body for POST /masterdb/etl/jobs/gater. Without a body, every kommune is fetched.
public record EtlJobRequest(

	@Schema(description = "Kommune numbers to fetch streets for. Left out: every kommune in the database.",
			example = "[\"4601\"]")
	@NotEmpty @Size(max = 500)
	List<@Pattern(regexp = "[0-9]{4}", message = "kommunenr must be 4 digits") String> kommunenr
)
{
}
