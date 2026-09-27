# syntax=docker/dockerfile:1
#
# Base Legal application image (docs/THREAT_MODEL.md S7, S12):
#   * multi-stage: build tools and caches never reach the runtime image;
#   * base images pinned by digest;
#   * the local query model (voyage-4-nano) is downloaded at BUILD time and
#     every file is checked against the pinned revision + SHA-256
#     (src/base_legal/embeddings/voyage-4-nano.lock.json); the runtime is
#     offline for models and re-verifies the hashes on every load;
#   * runs as an unprivileged user.
#
# The base image digest is an ARG so it can be pulled from a mirror of the
# same content (e.g. mirror.gcr.io/library/python) when Docker Hub rate-limits.
#
# Behind a TLS-intercepting proxy, pass its CA as a build secret (never stored
# in a layer) plus Docker's predefined proxy build args:
#   docker build --secret id=extra_ca,src=/path/ca.pem \
#     --build-arg HTTPS_PROXY=http://proxy:3128 --network host .
ARG PYTHON_IMAGE=python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.8.17@sha256:e4644cb5bd56fdc2c5ea3ee0525d9d21eed1603bccd6a21f887a938be7e85be1

FROM ${UV_IMAGE} AS uv

# --- build: dependencies and the project into /app/.venv --------------------
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    uv sync --locked --no-dev --extra local --no-install-project
COPY README.md LICENSE ./
COPY src ./src
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    uv sync --locked --no-dev --extra local --no-editable

# --- model: download and verify the pinned weights --------------------------
FROM build AS model
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    BASE_LEGAL_MODELS_DIR=/models /app/.venv/bin/base-legal model fetch

# --- runtime ---------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime
LABEL org.opencontainers.image.title="Base Legal" \
      org.opencontainers.image.description="Verified-citation Q&A over Brazilian data protection law. Not legal advice." \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/lucianocf/base-legal"
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --no-create-home app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=model /models /app/models
COPY corpus/manifest.yaml corpus/*.json /app/corpus/
COPY evals /app/evals
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HOME=/tmp/hf \
    BASE_LEGAL_MODELS_DIR=/app/models \
    BASE_LEGAL_CORPUS_DIR=/app/corpus
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]
# 0.0.0.0 inside the container only; compose publishes the port on 127.0.0.1.
CMD ["base-legal", "serve", "--host", "0.0.0.0", "--port", "8000"]
