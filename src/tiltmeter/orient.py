"""Which end of the axis is politically left, and which is right?

The selection axis (signals/selection.py) has an arbitrary sign — the math
doesn't know left from right. Orientation comes from public records
(METHODOLOGY.md D5): we embed Democratic and Republican floor speeches from
the Congressional Record, compute each outlet's average article embedding,
and check which axis pole sits closer in language to which party. If the
axis is backwards, we flip it. Convention: negative = left, positive = right
(matches how AllSides and Ad Fontes draw their scales).

The strength of the axis↔party-language agreement is reported as a
diagnostic: a weak agreement means orientation (and possibly the axis
itself) shouldn't be trusted, and the output says so rather than hiding it.
"""

import hashlib
import sqlite3
from dataclasses import dataclass

import numpy as np

SPEECH_EMBED_WORDS = 200  # MiniLM reads ~256 tokens; the opening covers the topic
MIN_ABS_CORRELATION = 0.3  # below this, orientation is flagged unreliable


@dataclass(frozen=True)
class Orientation:
    sign: int  # +1 keep, -1 flip
    correlation: float  # spearman rho between axis and party-language proxy
    reliable: bool
    proxy_by_outlet: tuple[float, ...]  # cos-to-R minus cos-to-D per outlet


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = np.argsort(np.argsort(a)).astype(np.float64)
    rb = np.argsort(np.argsort(b)).astype(np.float64)
    ra -= ra.mean()
    rb -= rb.mean()
    denom = np.sqrt((ra**2).sum() * (rb**2).sum())
    return float((ra * rb).sum() / denom) if denom > 0 else 0.0


def _cached_embed_texts(conn: sqlite3.Connection, texts: list[str]) -> np.ndarray:
    """Embed with the same fingerprint-keyed cache articles use."""
    from tiltmeter import embed

    hashes = [hashlib.sha256(t.encode()).hexdigest() for t in texts]
    conn.executescript(embed.CACHE_SCHEMA)
    cached = {}
    for h in hashes:
        row = conn.execute(
            "SELECT vector FROM embeddings WHERE content_hash = ? AND model = ?",
            (h, embed.MODEL_NAME),
        ).fetchone()
        if row:
            cached[h] = np.frombuffer(row[0], dtype=np.float32)
    missing = [(h, t) for h, t in zip(hashes, texts) if h not in cached]
    if missing:
        vectors = embed.embed_texts([t for _, t in missing])
        conn.executemany(
            "INSERT OR IGNORE INTO embeddings (content_hash, model, vector) VALUES (?, ?, ?)",
            [(h, embed.MODEL_NAME, v.tobytes()) for (h, _), v in zip(missing, vectors)],
        )
        conn.commit()
        cached.update({h: v for (h, _), v in zip(missing, vectors)})
    return np.stack([cached[h] for h in hashes])


def party_means(conn: sqlite3.Connection) -> dict[str, np.ndarray]:
    """Average embedding of each party's floor speeches (unit-normalized)."""
    rows = conn.execute("SELECT party, text FROM reference_speeches").fetchall()
    if not rows:
        raise ValueError("no reference speeches; run: tiltmeter reference")
    means = {}
    for party in ("D", "R"):
        texts = [
            " ".join(text.split()[:SPEECH_EMBED_WORDS])
            for p, text in rows
            if p == party
        ]
        if len(texts) < 20:
            raise ValueError(f"only {len(texts)} {party} speeches; reference corpus too thin")
        mean = _cached_embed_texts(conn, texts).mean(axis=0)
        means[party] = mean / np.linalg.norm(mean)
    return means


def outlet_proxy(
    outlet_vectors: dict[str, np.ndarray], means: dict[str, np.ndarray]
) -> dict[str, float]:
    """Per outlet: cosine-to-Republican minus cosine-to-Democratic language."""
    proxy = {}
    for outlet, vec in outlet_vectors.items():
        unit = vec / np.linalg.norm(vec)
        proxy[outlet] = float(unit @ means["R"] - unit @ means["D"])
    return proxy


def orient_sign(axis_positions: list[float], proxy_values: list[float]) -> Orientation:
    """Pure decision: flip the axis if it anti-correlates with party language."""
    rho = _spearman(np.asarray(axis_positions), np.asarray(proxy_values))
    return Orientation(
        sign=-1 if rho < 0 else 1,
        correlation=rho,
        reliable=abs(rho) >= MIN_ABS_CORRELATION,
        proxy_by_outlet=tuple(float(p) for p in proxy_values),
    )
