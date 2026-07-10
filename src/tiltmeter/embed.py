"""How does the pipeline see that two articles are about the same story?

Each article's headline + opening text is turned into an embedding — a vector
of numbers where similar texts land close together. Embeddings are used ONLY
to group similar articles (and to compare poles of the axis to congressional
language); they never judge anything (METHODOLOGY.md D8).

The model is pinned by name and revision and runs on CPU so that anyone,
anywhere, reproduces the same vectors. Vectors are cached in SQLite keyed by
content fingerprint: an article's embedding is computed once, ever.
"""

import sqlite3

import numpy as np

# Pinned embedding model (METHODOLOGY.md D3, tunable; see sensitivity sweep D7).
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"
LEDE_WORDS = 40  # headline + this many words of body ≈ headline + lede

_model = None  # loaded lazily: importing torch takes seconds and tests may not need it

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS embeddings (
    content_hash TEXT NOT NULL,
    model TEXT NOT NULL,
    vector BLOB NOT NULL,
    PRIMARY KEY (content_hash, model)
);
"""


def passage(title: str, text: str | None, summary: str | None) -> str:
    """The text we embed: headline plus lede (or feed summary as fallback)."""
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


def embed_hashes(conn: sqlite3.Connection, content_hashes: list[str]) -> np.ndarray:
    """Embeddings for articles named by fingerprint, using/filling the cache.

    Passage text (headline + lede) comes from the local articles table — the
    manifest deliberately carries no text (METHODOLOGY.md D9), so embedding a
    published manifest requires the locally collected corpus behind it.
    Row order follows content_hashes.
    """
    conn.executescript(CACHE_SCHEMA)
    cached: dict[str, np.ndarray] = {}
    for row in conn.execute(
        "SELECT content_hash, vector FROM embeddings WHERE model = ?", (MODEL_NAME,)
    ):
        cached[row[0]] = np.frombuffer(row[1], dtype=np.float32)

    missing = [h for h in content_hashes if h not in cached]
    if missing:
        placeholders = ",".join("?" * len(missing))
        rows = conn.execute(
            f"SELECT content_hash, title, text, summary FROM articles"
            f" WHERE content_hash IN ({placeholders})",
            missing,
        ).fetchall()
        found = {r[0]: passage(r[1], r[2], r[3]) for r in rows}
        absent = [h for h in missing if h not in found]
        if absent:
            raise ValueError(
                f"{len(absent)} manifest articles not in local corpus (first: {absent[0]})"
            )
        order = [h for h in missing]
        vectors = embed_texts([found[h] for h in order])
        conn.executemany(
            "INSERT OR IGNORE INTO embeddings (content_hash, model, vector) VALUES (?, ?, ?)",
            [(h, MODEL_NAME, v.tobytes()) for h, v in zip(order, vectors)],
        )
        conn.commit()
        cached.update(dict(zip(order, vectors)))
    return np.stack([cached[h] for h in content_hashes])
