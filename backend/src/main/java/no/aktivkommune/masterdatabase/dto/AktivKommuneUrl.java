package no.aktivkommune.masterdatabase.dto;

import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

// The only kind of booking URL the API accepts: https://<name>.aktiv-kommune.no,
// one subdomain label, no path, query or port. The ETL fetches data from the
// URL that is stored, so anything else would let a caller make the ETL request
// arbitrary hosts. The ETL checks the same rule when it reads the list
// (etl/helpers.py); keep the two in step.
//
// The key format "aktiv-kommune:<name>" is the one etl/synk.py and
// etl/last_inn.py write to fagsystem_instans.kildenokkel.
public final class AktivKommuneUrl
{
	public static final String REGEX = "^https://([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)\\.aktiv-kommune\\.no/?$";
	public static final String KILDENOKKEL_PREFIX = "aktiv-kommune:";

	private static final Pattern PATTERN = Pattern.compile(REGEX, Pattern.CASE_INSENSITIVE);

	private AktivKommuneUrl()
	{
	}

	// The subdomain in lower case ("bergen"), or null if the URL is not accepted.
	public static String slugOf(String url)
	{
		if (url == null)
		{
			return null;
		}
		Matcher m = PATTERN.matcher(url.strip());
		return m.matches() ? m.group(1).toLowerCase(Locale.ROOT) : null;
	}

	public static String baseUrlOf(String slug)
	{
		return "https://" + slug + ".aktiv-kommune.no";
	}

	public static String kildenokkelOf(String slug)
	{
		return KILDENOKKEL_PREFIX + slug;
	}
}
