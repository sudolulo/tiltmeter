"""How does the pipeline see that two texts are alike?

Texts are turned into embeddings — vectors where similar texts land close
together. Embeddings only ever *group* text (story clustering, axis
orientation); they never judge anything (METHODOLOGY.md D8).

One cache, one rule: a vector is stored under the SHA-256 of the exact text
that was embedded, plus the exact model name@revision that embedded it.
Change the passage recipe, the model, or the pinned revision and every key
changes with it — the cache cannot serve a stale or mismatched vector, by
construction. Lookups are chunked queries proportional to the request, never
scans of the whole cache.
"""

import hashlib
import sqlite3

import numpy as np

# Pinned embedding model (METHODOLOGY.md D3, tunable; see sensitivity sweep D7).
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"
LEDE_WORDS = 40  # headline + this many words of body ≈ headline + lede

# The cache key's model column carries the full pin: bumping the revision can
# never silently reuse old vectors.
CACHE_MODEL_KEY = f"{MODEL_NAME}@{MODEL_REVISION}"
_CHUNK = 400  # SQLite bound-parameter comfort zone

_model = None  # loaded lazily: importing torch takes seconds and tests may not need it

def passage(title: str, text: str | None, summary: str | None) -> str:
    """The text we embed for an article: headline plus lede (or feed summary
    as fallback). Everything read here comes from the fingerprinted payload."""
    body = text or summary or ""
    lede = " ".join(body.split()[:LEDE_WORDS])
    return f"{title}. {lede}".strip()


def _load_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION, device="cpu")
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed texts to unit-length float32 vectors (cosine-ready)."""
    model = _load_model()
    return model.encode(
        texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
    ).astype(np.float32)


def cached_embed(conn: sqlite3.Connection, texts: list[str]) -> np.ndarray:
    """Vectors for exact texts, using/filling the cache. Row order preserved.

    The single entry point for every cached embedding in the pipeline —
    articles and speeches alike — so the cache invariants live in one place.
    The cache table is created by db.connect (derived data, custody-exempt);
    no DDL happens here, so calling this mid-transaction can never implicitly
    commit a half-collected batch.
    """
    owns_transaction = not conn.in_transaction
    keys = [hashlib.sha256(t.encode("utf-8")).hexdigest() for t in texts]
    found: dict[str, np.ndarray] = {}
    unique = list(dict.fromkeys(keys))
    for i in range(0, len(unique), _CHUNK):
        chunk = unique[i : i + _CHUNK]
        placeholders = ",".join("?" * len(chunk))
        for row in conn.execute(
            f"SELECT text_hash, vector FROM embeddings"
            f" WHERE model = ? AND text_hash IN ({placeholders})",
            [CACHE_MODEL_KEY, *chunk],
        ):
            found[row[0]] = np.frombuffer(row[1], dtype=np.float32)
    by_key = dict(zip(keys, texts))
    missing = [k for k in unique if k not in found]
    if missing:
        vectors = embed_texts([by_key[k] for k in missing])
        conn.executemany(
            "INSERT OR IGNORE INTO embeddings (text_hash, model, vector) VALUES (?, ?, ?)",
            [(k, CACHE_MODEL_KEY, v.tobytes()) for k, v in zip(missing, vectors)],
        )
        if owns_transaction:
            conn.commit()  # inside a caller's batch, cache rows ride its commit
        found.update(dict(zip(missing, vectors)))
    return np.stack([found[k] for k in keys])


def embed_hashes(conn: sqlite3.Connection, content_hashes: list[str]) -> np.ndarray:
    """Embeddings for articles named by content fingerprint, in order.

    Passage text is rebuilt from the fingerprinted payload in the local
    contents table — the manifest deliberately carries no text (D9) — then
    embedded via the shared cache.
    """
    from tiltmeter import db

    unique = list(dict.fromkeys(content_hashes))
    payloads = db.get_contents(conn, unique)
    absent = [h for h in unique if h not in payloads]
    if absent:
        raise ValueError(
            f"{len(absent)} manifest articles not in local corpus (first: {absent[0]})"
        )
    passages = {
        chash: passage(*db.split_article_payload(payload))
        for chash, payload in payloads.items()
    }
    # cached_embed dedups and preserves row order itself
    return cached_embed(conn, [passages[h] for h in content_hashes])
