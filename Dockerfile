# tiltmeter: the whole pipeline in one reproducible image.
# The pinned embedding model is baked in at build time, so a container can
# recompute any release fully offline — part of the reproducibility story,
# not just packaging convenience.
#
# Default command serves the read-only API over /app/releases; the collector
# runs `tiltmeter cycle` on a sleep loop (see compose.yaml) so all
# orchestration logic lives in tested Python, not deployment shell.

FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /bin/

WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1

# dependency layer first: rebuilds only when the lockfile changes
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

# bake the pinned model BEFORE copying source, so day-to-day code changes
# never re-download it. The ARGs must match src/tiltmeter/embed.py — a test
# (tests/test_docs.py) fails the build pipeline if they drift.
ARG EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
ARG EMBED_REVISION=c9745ed1d9f207416be6d2e6f8de32d1f16199bf
ENV HF_HOME=/opt/hf-cache
RUN /app/.venv/bin/python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('${EMBED_MODEL}', revision='${EMBED_REVISION}', device='cpu')" \
    && chmod -R a+rX /opt/hf-cache

COPY src ./src
COPY config ./config
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
VOLUME ["/app/data", "/app/releases"]
EXPOSE 8477

ENTRYPOINT ["tiltmeter"]
CMD ["serve", "--releases", "releases"]
