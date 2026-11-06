package no.aktivkommune.masterdatabase.config;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@Component
public class ApiKeyFilter extends OncePerRequestFilter {

	private static final String HEADER = "X-API-KEY";
	private final String expectedKey;  // @Value("${masterdb.api-key}")

	public ApiKeyFilter(@Value("${masterdb.api-key}") String expectedKey)
	{
		this.expectedKey = expectedKey;
	}

	@Override
	protected boolean shouldNotFilter(HttpServletRequest request)
	{
		return !request.getRequestURI().startsWith("/masterdb/kommune");
	}


	@Override
	protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
			throws ServletException, IOException
	{
		String key = request.getHeader(HEADER);
		if (key == null || !MessageDigest.isEqual(
							key.getBytes(StandardCharsets.UTF_8),
							expectedKey.getBytes(StandardCharsets.UTF_8)))
		{
			response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
			return;
		}

		System.out.println("API key accepted for "+ request.getRequestURI());
		filterChain.doFilter(request, response);
	}

}
