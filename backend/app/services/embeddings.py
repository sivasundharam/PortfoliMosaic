from typing import List
import os
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover
    SentenceTransformer = None  # type: ignore


class Embeddings:
    def __init__(self):
        self.provider = os.getenv("EMBEDDING_PROVIDER", "sentence_transformers")
        self.model_name = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        self.model = None
        if self.provider == "sentence_transformers" and SentenceTransformer is not None:
            try:
                self.model = SentenceTransformer(self.model_name)
            except Exception:
                self.model = None

    def embed(self, texts: List[str]) -> np.ndarray:
        if self.model is not None:
            return np.asarray(self.model.encode(texts, convert_to_numpy=True))
        # Fallback: simple hash-based pseudo-embeddings
        dim = 384
        vectors = []
        for t in texts:
            rng = np.random.default_rng(abs(hash(t)) % (2**32))
            vectors.append(rng.standard_normal(dim))
        return np.vstack(vectors)
