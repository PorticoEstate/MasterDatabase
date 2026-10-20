# Multi-stage build: kompilerer backend/ med Maven, kjører på en slank JRE.
# Python 3 legges til i runtime-steget (stdlib only, se etl/README.md) slik at
# samme container kan kjøre etl/last_inn.py for admin-trigger-funksjonen
# (se backend/service/EtlTriggerService.java).

FROM maven:3.9-eclipse-temurin-21 AS build

ARG http_proxy
ARG https_proxy
ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}

WORKDIR /build

# Henter avhengigheter i et eget lag først, slik at "mvn package" ikke må
# laste ned alt på nytt for hver kodeendring.
COPY backend/pom.xml .
RUN mvn -q -B dependency:go-offline

COPY backend/src ./src
RUN mvn -q -B package -DskipTests

# ---------------------------------------------------------------------------

FROM eclipse-temurin:21-jre

ARG http_proxy
ARG https_proxy
ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Capgemini/Zscaler bryter opp og signerer om all utgående HTTPS-trafikk på
# nett med sitt eget rotsertifikat (se memory "wsl-ca-sertifikat-lost").
# Containeren har sitt eget, separate tillitslager - uten dette feiler
# etl/last_inn.py sine kall mot Aktiv kommune med
# "self-signed certificate in certificate chain".
COPY build_config/capgemini-ca/*.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates

WORKDIR /app
COPY --from=build /build/target/masterdb-api.jar app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
