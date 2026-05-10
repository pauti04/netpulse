# Multi-stage build for the NetPulse FastAPI surface.
#
# The image bundles the bundled real-data fixture (data/fixtures/) and
# the focused YouTube RIB baseline (data/baselines/) so `netpulse serve`
# answers /detect/bgp queries against the canonical incident out of the
# box. libBGPStream + pybgpstream are NOT installed in the image; the
# server doesn't ingest, it just queries pre-built DuckDB stores.

FROM python:3.12-slim AS build

ENV UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# uv via the official installer (smallest reliable footprint).
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    cp /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --shell /bin/bash netpulse
WORKDIR /app

# Bring in the prepared venv from the build stage.
COPY --from=build /app/.venv /app/.venv
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY data/fixtures ./data/fixtures
COPY data/baselines ./data/baselines

USER netpulse
EXPOSE 8000

# Default: serve against the bundled YouTube fixture + RIB baseline.
# fly.toml or `docker run` can override the CMD to point at different
# stores once they are mounted as volumes.
CMD ["netpulse", "serve", \
     "--store", "/app/data/fixtures/youtube_2008_demo.duckdb", \
     "--baseline", "/app/data/baselines/yt_rib_filtered.duckdb", \
     "--host", "0.0.0.0", \
     "--port", "8000"]
