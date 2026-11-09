FROM eclipse-temurin:25-jdk AS build
WORKDIR /src

# Proxy brukes av mvnw og Maven når bygget kjører bak bedriftsproxy.
ARG http_proxy
ARG https_proxy
ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}

COPY .mvn .mvn
COPY mvnw pom.xml ./
RUN chmod +x mvnw \
	&& proxy="${https_proxy:-${http_proxy:-}}" \
	&& mkdir -p /root/.m2 \
	&& printf '<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"></settings>\n' > /root/.m2/settings.xml \
	&& if [ -n "$proxy" ]; then \
		case "$proxy" in \
			https://*) default_port=443 ;; \
			http://*) default_port=80 ;; \
			*) echo "Proxy URL must start with http:// or https://" >&2; exit 1 ;; \
		esac; \
		authority="${proxy#*://}"; \
		authority="${authority%%/*}"; \
		authority="${authority##*@}"; \
		proxy_host="${authority%%:*}"; \
		proxy_port="${authority##*:}"; \
		if [ "$proxy_host" = "$proxy_port" ]; then proxy_port="$default_port"; fi; \
		export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Dhttp.proxyHost=$proxy_host -Dhttp.proxyPort=$proxy_port -Dhttps.proxyHost=$proxy_host -Dhttps.proxyPort=$proxy_port"; \
		printf '<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"><proxies><proxy><id>build-proxy</id><active>true</active><protocol>%s</protocol><host>%s</host><port>%s</port></proxy></proxies></settings>\n' "${proxy%%://*}" "$proxy_host" "$proxy_port" > /root/.m2/settings.xml; \
	fi \
	&& ./mvnw -q -s /root/.m2/settings.xml dependency:go-offline
COPY src src
RUN ./mvnw -q -s /root/.m2/settings.xml package -DskipTests

FROM eclipse-temurin:25-jre
WORKDIR /app
COPY --from=build /src/target/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
