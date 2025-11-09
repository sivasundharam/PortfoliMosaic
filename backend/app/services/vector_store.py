import os
import faiss  # type: ignore
import numpy as np
import json
import pickle
from typing import List, Tuple, Dict, Any


class VectorStore:
    def __init__(self, index_dir: str, dim: int = 384):
        self.index_dir = index_dir
        self.index_path = os.path.join(index_dir, "index.faiss")
        self.metadata_path = os.path.join(index_dir, "metadata.pkl")
        self.dim = dim
        os.makedirs(index_dir, exist_ok=True)
        if os.path.exists(self.index_path):
            self.index = faiss.read_index(self.index_path)
            if os.path.exists(self.metadata_path):
                with open(self.metadata_path, "rb") as f:
                    self.chunks_metadata = pickle.load(f)
            else:
                self.chunks_metadata = []
        else:
            self.index = faiss.IndexFlatIP(dim)
            self.chunks_metadata = []

    def add(self, vectors: np.ndarray, chunks_metadata: List[Dict[str, Any]] = None):
        norms = np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-12
        normalized = vectors / norms
        self.index.add(normalized.astype(np.float32))
        if chunks_metadata:
            start_idx = len(self.chunks_metadata)
            for i, meta in enumerate(chunks_metadata):
                meta["vector_id"] = start_idx + i
            self.chunks_metadata.extend(chunks_metadata)
        faiss.write_index(self.index, self.index_path)
        with open(self.metadata_path, "wb") as f:
            pickle.dump(self.chunks_metadata, f)

    def search(self, query_vectors: np.ndarray, k: int = 4, session_id: str = None) -> Tuple[np.ndarray, np.ndarray]:
        """Search for similar vectors, optionally filtered by session_id"""
        norms = np.linalg.norm(query_vectors, axis=1, keepdims=True) + 1e-12
        normalized = query_vectors / norms

        # If session_id is provided, we need to filter results
        if session_id:
            # DEBUG: Log search details
            print(f"      [VectorStore.search] Total chunks in store: {len(self.chunks_metadata)}")
            print(f"      [VectorStore.search] Searching for session: {session_id}")

            # Search for more results than needed to account for filtering
            # Increase multiplier to 100 to handle cases where target chunk has low similarity
            search_k = min(k * 100, len(self.chunks_metadata))
            scores, ids = self.index.search(normalized.astype(np.float32), search_k)

            print(f"      [VectorStore.search] FAISS returned {len(ids[0])} results")

            # Filter by session_id
            filtered_scores = []
            filtered_ids = []
            for score, idx in zip(scores[0], ids[0]):
                if 0 <= idx < len(self.chunks_metadata):
                    chunk_meta = self.chunks_metadata[int(idx)]
                    chunk_session = chunk_meta.get("session_id")
                    print(f"      [VectorStore.search] Chunk {idx}: session={chunk_session}, score={score:.4f}, match={chunk_session == session_id}")
                    if chunk_session == session_id:
                        filtered_scores.append(score)
                        filtered_ids.append(idx)
                        if len(filtered_ids) >= k:
                            break

            print(f"      [VectorStore.search] Filtered to {len(filtered_ids)} chunks")

            # Return only real chunks (no padding with fake chunks)
            # If we have fewer than k results, that's fine - return what we have
            if len(filtered_ids) == 0:
                return np.array([[]]), np.array([[]])

            return np.array([filtered_scores]), np.array([filtered_ids])
        else:
            # No filtering, return all results
            scores, ids = self.index.search(normalized.astype(np.float32), k)
            return scores, ids

    def get_chunks_by_ids(self, ids: np.ndarray) -> List[Dict[str, Any]]:
        chunks = []
        for idx in ids[0]:
            if 0 <= idx < len(self.chunks_metadata):
                chunks.append(self.chunks_metadata[int(idx)])
        return chunks
