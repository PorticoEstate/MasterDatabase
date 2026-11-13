package no.aktivkommune.masterdatabase.service;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.server.ResponseStatusException;

import no.aktivkommune.masterdatabase.dto.EtlJob;
import no.aktivkommune.masterdatabase.dto.EtlJobAccepted;

// Client for the job server in the etl container (etl/jobserver.py). The calls only
// queue a job or read its status; the jobs themselves run in the etl container, so
// short timeouts are enough. The ETL API has no authentication: it is reachable only
// on the compose network (the etl service must never get a `ports:` mapping).
//
// Failures become ResponseStatusException without the internal URL in the message:
// etl unreachable or too slow -> 503, etl 400 -> 400, etl 404 -> 404, anything else -> 502.
@Service
public class EtlClient
{
	private static final Logger log = LoggerFactory.getLogger(EtlClient.class);

	private final RestClient client;

	public EtlClient(@Value("${etl.url}") String baseUrl)
	{
		HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
		JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(http);
		factory.setReadTimeout(Duration.ofSeconds(5));
		this.client = RestClient.builder().baseUrl(baseUrl).requestFactory(factory).build();
	}

	// type must be sync, geocode or gater (the caller validates it; the ETL checks again).
	// kommunenr only applies to gater; empty means every kommune.
	public EtlJobAccepted enqueue(String type, List<String> kommunenr)
	{
		return call(() ->
		{
			RestClient.RequestBodySpec request = client.post().uri("/jobs/{type}", type);
			if (kommunenr != null && !kommunenr.isEmpty())
			{
				request = request.contentType(MediaType.APPLICATION_JSON).body(Map.of("kommunenr", kommunenr));
			}
			return request.retrieve().body(EtlJobAccepted.class);
		});
	}

	public EtlJob get(String id)
	{
		return call(() -> client.get().uri("/jobs/{id}", id).retrieve().body(EtlJob.class));
	}

	public List<EtlJob> list()
	{
		return call(() -> client.get().uri("/jobs").retrieve().body(new org.springframework.core.ParameterizedTypeReference<List<EtlJob>>() {}));
	}

	//generic call function to cath common exceptions and throw cleaner response status exception handled by the controller
	private <T> T call(Supplier<T> request)
	{
		try
		{
			return request.get();
		}
		catch (ResourceAccessException e)
		{
			log.warn("The etl service is unreachable or timed out: {}", e.getMessage());
			throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "The ETL service is not available");
		}
		catch (RestClientResponseException e)
		{
			log.warn("The etl service answered {}: {}", e.getStatusCode(), e.getResponseBodyAsString());
			if (e.getStatusCode().value() == 400)
			{
				throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "The ETL service rejected the request");
			}
			if (e.getStatusCode().value() == 404)
			{
				throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No such ETL job or job type");
			}
			throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Unexpected answer from the ETL service");
		}
		catch (RestClientException e)
		{
			log.warn("Unreadable answer from the etl service: {}", e.getMessage());
			throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Unexpected answer from the ETL service");
		}
	}
}
