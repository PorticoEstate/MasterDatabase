package no.aktivkommune.masterdatabase.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

// Tittel og beskrivelse øverst i den genererte OpenAPI-spesifikasjonen og Swagger UI.
@Configuration
public class OpenApiConfig
{
	@Bean
	public OpenAPI masterDbOpenApi()
	{
		return new OpenAPI().info(new Info()
				.title("MasterDB search API")
				.version("v1")
				.description("Search across municipalities. Returns hits and links to the local booking system. "
						+ "Never checks availability or books anything."));
	}
}
