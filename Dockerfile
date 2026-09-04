# syntax=docker/dockerfile:1@sha256:bde3983e9c939224420ddaf6b784cc30e09b035a4dea01f581230c50809f372e

ARG PYTHON_IMAGE=python:3.14.7-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6

FROM ${PYTHON_IMAGE} AS builder

RUN pip install --no-cache-dir uv==0.12.5
WORKDIR /app

COPY .build/libraries/*.whl /wheels/
COPY .build/requirements.txt /wheels/
COPY dist/groovemap_mcp_server-*.whl /wheels/

RUN uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python --require-hashes --requirements /wheels/requirements.txt && \
    uv pip install --python /app/.venv/bin/python --no-deps /wheels/*.whl && \
    find /app/.venv -type f -name '*.py[co]' -delete && \
    find /app/.venv -type d -name __pycache__ -prune -exec rm -rf '{}' +

FROM ${PYTHON_IMAGE}

ARG BUILD_DATE
ARG BUILD_VERSION=0.1.0
ARG VCS_REF

RUN case "${VCS_REF}" in *[!0-9a-f]*|"") exit 1 ;; esac && \
    [ "${#VCS_REF}" -eq 40 ]

LABEL org.opencontainers.image.title="mcp-server" \
      org.opencontainers.image.description="Model Context Protocol adapter for the GrooveMap catalog" \
      org.opencontainers.image.authors="Robert Wlodarczyk <robert@simplicityguy.com>" \
      org.opencontainers.image.url="https://groovemap.music" \
      org.opencontainers.image.documentation="https://github.com/groovemap-music/mcp-server/blob/main/README.md" \
      org.opencontainers.image.source="https://github.com/groovemap-music/mcp-server" \
      org.opencontainers.image.vendor="GrooveMap" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${BUILD_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.base.name="docker.io/library/python:3.14.7-slim"

RUN groupadd --gid 1000 groovemap && \
    useradd --uid 1000 --gid groovemap --create-home --shell /usr/sbin/nologin groovemap && \
    mkdir -p /app && \
    chown -R 1000:1000 /app

WORKDIR /app
COPY --from=builder --chown=1000:1000 /app/.venv /app/.venv

ENV HOME=/home/groovemap \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

USER 1000:1000
ENTRYPOINT ["/app/.venv/bin/groovemap-mcp"]
CMD ["--transport", "streamable-http"]
