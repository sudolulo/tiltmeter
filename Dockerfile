# tiltmeter: the whole pipeline in one reproducible image.
# The pinned embedding model is baked in at build time, so a container can
# recompute any release fully offline — part of the reproducibility story,
# not just packaging convenience.
#
# Default command serves the read-only API over /app/releases; every other
# pipeline stage is available as a one-shot command, e.g.:
#   docker compose run --rm tiltmeter ingest
#   docker compose run --rm tiltmeter run --manifest releases/manifest-<id>.json

FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /bin/

WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1

# dependency layer first: rebuilds only when the lockfile changes
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY config ./config
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# bake the pinned model so runs need no network and no HF account; cache must
# be world-readable because deployments run the pipeline as a non-root uid
ENV HF_HOME=/opt/hf-cache
RUN /app/.venv/bin/python -c "from tiltmeter import embed; embed._load_model()" \
    && chmod -R a+rX /opt/hf-cache

ENV PATH="/app/.venv/bin:$PATH"
VOLUME ["/app/data", "/app/releases"]
EXPOSE 8477

ENTRYPOINT ["tiltmeter"]
CMD ["serve", "--releases", "releases"]
