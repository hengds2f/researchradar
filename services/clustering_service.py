"""Semantic Clustering Service

Transforms per-paper embeddings into a 2-D scatter map with cluster labels.

Pipeline
--------
1. Average chunk embeddings → one vector per paper
2. L2-normalise
3. Dimensionality reduction: UMAP (preferred) → PCA (numpy fallback)
4. Clustering: HDBSCAN (preferred) → KMeans → single-cluster fallback
5. Build enriched point records + summary stats

Results are cached by a SHA-256 fingerprint of the corpus and returned
immediately on subsequent calls without recomputation.  The cache is
invalidated whenever papers are added, deleted, or the session is cleared.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional heavy imports — fall back gracefully when not installed
# ---------------------------------------------------------------------------
try:
    import umap as _umap_lib   # umap-learn package
    _UMAP_AVAILABLE = True
except ImportError:
    _UMAP_AVAILABLE = False

try:
    import hdbscan as _hdbscan_lib
    _HDBSCAN_AVAILABLE = True
except ImportError:
    _HDBSCAN_AVAILABLE = False

try:
    from sklearn.cluster import KMeans
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

_YEAR_RE = re.compile(r'\b(19|20)\d{2}\b')

# Distinct palette for up to 20 clusters (hex, pairs well with dark bg)
CLUSTER_COLORS = [
    "#3b82f6", "#8b5cf6", "#06b6d4", "#10b981", "#f59e0b",
    "#ef4444", "#ec4899", "#14b8a6", "#a855f7", "#f97316",
    "#84cc16", "#0ea5e9", "#6366f1", "#22d3ee", "#fb923c",
    "#e879f9", "#34d399", "#fbbf24", "#60a5fa", "#f43f5e",
]
OUTLIER_COLOR = "#475569"


class ClusteringService:
    """Stateless service with a single in-memory result cache."""

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(
        self,
        papers_meta: list[dict],
        embeddings_map: dict[str, np.ndarray],
    ) -> dict[str, Any]:
        """Return the 2-D clustering map (from cache when possible).

        Parameters
        ----------
        papers_meta:
            List of paper dicts with at least ``id``, ``title``, ``filename``.
        embeddings_map:
            Mapping ``{paper_id: ndarray of shape (D,)}``.
        """
        paper_ids = sorted(embeddings_map.keys())
        cache_key = self._make_cache_key(paper_ids)

        if cache_key in self._cache:
            return self._cache[cache_key]

        result = self._compute_uncached(papers_meta, embeddings_map, cache_key)
        self._cache[cache_key] = result
        return result

    def invalidate_for_papers(self, paper_ids: list[str]) -> None:
        """Drop all cache entries that include any of the given paper IDs.

        Called when papers are added, deleted, or the session is cleared.
        """
        to_remove = [k for k in self._cache if any(pid in k for pid in paper_ids)]
        for k in to_remove:
            del self._cache[k]

    # ------------------------------------------------------------------
    # Core computation
    # ------------------------------------------------------------------

    @staticmethod
    def _make_cache_key(paper_ids: list[str]) -> str:
        combined = "|".join(sorted(paper_ids))
        return hashlib.sha256(combined.encode()).hexdigest()[:24]

    def _compute_uncached(
        self,
        papers_meta: list[dict],
        embeddings_map: dict[str, np.ndarray],
        cache_key: str,
    ) -> dict[str, Any]:
        paper_ids = list(embeddings_map.keys())
        n = len(paper_ids)

        # Build (n × D) matrix and L2-normalise
        X = np.stack([embeddings_map[pid] for pid in paper_ids])
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        X_norm = (X / norms).astype(np.float32)

        coords, reduction_method = self._reduce(X_norm, n)
        labels, clustering_method = self._cluster(X_norm, n)

        meta_by_id = {p["id"]: p for p in papers_meta}

        # Per-cluster centroid (used for similarity scoring)
        cluster_centroids: dict[int, np.ndarray] = {}
        for cid in set(labels):
            if cid < 0:
                continue
            mask = labels == cid
            cluster_centroids[cid] = X_norm[mask].mean(axis=0)

        points: list[dict] = []
        for i, pid in enumerate(paper_ids):
            meta = meta_by_id.get(pid, {})
            cid = int(labels[i])
            is_outlier = cid < 0

            # Cosine similarity to own cluster centroid
            sim_score: float | None = None
            if not is_outlier and cid in cluster_centroids:
                emb = X_norm[i]
                c = cluster_centroids[cid]
                denom = float(np.linalg.norm(emb)) * float(np.linalg.norm(c))
                sim_score = float(np.dot(emb, c)) / (denom + 1e-8)

            year = self._extract_year(
                meta.get("title", "") + " " + meta.get("filename", "")
            )

            points.append(
                {
                    "id": pid,
                    "title": meta.get("title", "Untitled"),
                    "authors": meta.get("authors", "Unknown"),
                    "year": year,
                    "x": float(coords[i, 0]),
                    "y": float(coords[i, 1]),
                    "cluster_id": cid,
                    "cluster_label": f"Cluster {cid}" if cid >= 0 else "Outlier",
                    "is_outlier": is_outlier,
                    "similarity_score": round(sim_score, 4) if sim_score is not None else None,
                    "color": CLUSTER_COLORS[cid % len(CLUSTER_COLORS)] if cid >= 0 else OUTLIER_COLOR,
                }
            )

        label_counts = Counter(int(l) for l in labels)
        clusters = [
            {
                "id": cid,
                "label": f"Cluster {cid}",
                "size": label_counts[cid],
                "color": CLUSTER_COLORS[cid % len(CLUSTER_COLORS)],
            }
            for cid in sorted(k for k in label_counts if k >= 0)
        ]

        outlier_count = label_counts.get(-1, 0)
        sizes = [c["size"] for c in clusters]

        return {
            "points": points,
            "clusters": clusters,
            "stats": {
                "n_papers": n,
                "n_clusters": len(clusters),
                "largest_cluster_size": max(sizes) if sizes else 0,
                "outlier_count": outlier_count,
            },
            "method": {
                "reduction": reduction_method,
                "clustering": clustering_method,
            },
            "cache_key": cache_key,
        }

    # ------------------------------------------------------------------
    # Dimensionality reduction
    # ------------------------------------------------------------------

    def _reduce(self, X: np.ndarray, n: int) -> tuple[np.ndarray, str]:
        """Reduce to 2-D.  UMAP → PCA → random fallback."""
        if _UMAP_AVAILABLE and n >= 4:
            try:
                n_neighbors = min(15, n - 1)
                reducer = _umap_lib.UMAP(
                    n_components=2,
                    n_neighbors=n_neighbors,
                    min_dist=0.1,
                    metric="cosine",
                    random_state=42,
                    low_memory=n > 500,
                )
                coords = reducer.fit_transform(X)
                return coords.astype(float), "umap"
            except Exception as exc:
                logger.warning("UMAP failed (%s); falling back to PCA", exc)

        try:
            return self._pca_2d(X), "pca"
        except Exception as exc:
            logger.warning("PCA failed (%s); using random layout", exc)
            rng = np.random.default_rng(42)
            return rng.standard_normal((n, 2)), "random"

    @staticmethod
    def _pca_2d(X: np.ndarray) -> np.ndarray:
        """2-component PCA via truncated SVD (numpy only)."""
        X_c = X - X.mean(axis=0)
        _, _, Vt = np.linalg.svd(X_c, full_matrices=False)
        return (X_c @ Vt[:2].T).astype(float)

    # ------------------------------------------------------------------
    # Clustering
    # ------------------------------------------------------------------

    def _cluster(self, X: np.ndarray, n: int) -> tuple[np.ndarray, str]:
        """Assign cluster labels.  HDBSCAN → KMeans → single-cluster."""
        if _HDBSCAN_AVAILABLE and n >= 4:
            try:
                min_cs = max(2, min(5, n // 4))
                clusterer = _hdbscan_lib.HDBSCAN(
                    min_cluster_size=min_cs,
                    metric="euclidean",
                    cluster_selection_method="eom",
                )
                labels = clusterer.fit_predict(X)
                unique = set(labels.tolist())
                # Accept result unless every point is an outlier
                if len(unique) > 1 or (len(unique) == 1 and -1 not in unique):
                    return labels, "hdbscan"
                logger.info(
                    "HDBSCAN marked all points as outliers; falling back to KMeans"
                )
            except Exception as exc:
                logger.warning("HDBSCAN failed (%s); falling back to KMeans", exc)

        if _SKLEARN_AVAILABLE and n >= 2:
            try:
                k = min(max(2, n // 3), 8)
                km = KMeans(n_clusters=k, random_state=42, n_init=10)
                return km.fit_predict(X), "kmeans"
            except Exception as exc:
                logger.warning("KMeans failed (%s); using single cluster", exc)

        return np.zeros(n, dtype=int), "single"

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_year(text: str) -> int | None:
        """Return the first 4-digit year (1900–2099) found in *text*, or None."""
        m = _YEAR_RE.search(text)
        return int(m.group()) if m else None
