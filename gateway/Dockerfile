FROM ghcr.io/berriai/litellm@sha256:a3715fa7ad8387941ab697259bd2881d68931657247a41984f90fae6d11c62bf

COPY gateway/litellm-config.yaml /app/litellm-config.yaml

ENV NO_DOCS=True
ENV NO_REDOC=True
ENV NO_OPENAPI=True

EXPOSE 4000

CMD ["--config", "/app/litellm-config.yaml", "--host", "0.0.0.0", "--port", "4000", "--num_workers", "1", "--use_v2_migration_resolver"]