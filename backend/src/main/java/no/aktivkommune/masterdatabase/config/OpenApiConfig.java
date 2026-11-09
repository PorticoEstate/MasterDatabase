package no.aktivkommune.masterdatabase.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

// Tittel og beskrivelse øverst i den genererte OpenAPI-spesifikasjonen og Swagger UI.
// Deklarerer også API-nøkkelen (header X-API-KEY, sjekket av ApiKeyFilter) som et
// sikkerhetsskjema. Det er først controllerne som krever det, via @SecurityRequirement.
@Configuration
public class OpenApiConfig
{
	@Bean
	public OpenAPI masterDbOpenApi()
	{
		return new OpenAPI()
				.info(new Info()
						.title("MasterDB API")
						.version("v1")
						.description("Search across municipalities (returns hits and links to the local booking "
								+ "system, never checks availability or books anything), and administration of "
								+ "kommuner (requires an API key)."))
				.components(new Components().addSecuritySchemes("apiKey",
						new SecurityScheme()
								.type(SecurityScheme.Type.APIKEY)
								.in(SecurityScheme.In.HEADER)
								.name("X-API-KEY")));
	}
}
