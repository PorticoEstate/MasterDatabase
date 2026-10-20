package no.bergenkommune.masterdb.dev;

import java.nio.charset.StandardCharsets;
import java.util.Date;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.MACSigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

/**
 * IKKE en test - en liten hjelpeklasse for å generere et admin-JWT til lokal
 * manuell testing av /admin/**-endepunktene, siden det ikke finnes noen
 * identitetsleverandør ennå (se SecurityConfig). Kjør main() direkte fra IDE-
 * en, eller se backend/README.md for kommandolinje-varianten.
 *
 * Nøkkelen (args[0], ev. miljøvariabel JWT_SECRET) må matche
 * security.jwt.secret i den kjørende appen.
 */
public final class DevTokenPrinter {

    private DevTokenPrinter() {
    }

    public static void main(String[] args) throws Exception {
        String secret = args.length > 0 ? args[0] : "dev-only-change-me-dev-only-change-me";

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .subject("dev-admin")
            .claim("scope", "admin")
            .issueTime(new Date())
            .expirationTime(new Date(System.currentTimeMillis() + 3_600_000))
            .build();

        SignedJWT jwt = new SignedJWT(new JWSHeader(JWSAlgorithm.HS256), claims);
        jwt.sign(new MACSigner(secret.getBytes(StandardCharsets.UTF_8)));

        System.out.println(jwt.serialize());
    }
}
