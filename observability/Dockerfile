# ADR-006 / specs/013 T10 — OpenTelemetry Collector privado.
# Patrón equivalente a gateway/Dockerfile: Railway construye desde la raíz del
# repo, de modo que manifiesto e imagen se versionan y redespliegan juntos.
# Los secretos NO viven aquí: GRAFANA_OTLP_ENDPOINT y GRAFANA_OTLP_AUTHORIZATION
# se inyectan como variables/secrets de Railway (nunca en Git ni en logs).
FROM otel/opentelemetry-collector-contrib:0.138.0

COPY otel-collector.yaml /etc/otelcol/config.yaml

CMD ["--config=/etc/otelcol/config.yaml"]
