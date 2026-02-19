from __future__ import annotations

import logging
import pickle
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from campus_assistant.config import SETTINGS
from campus_assistant.data_models import Document

logger = logging.getLogger(__name__)


class VectorIndex:
    def __init__(self, embedding_backend: str | None = None) -> None:
        self.embedding_backend = embedding_backend or SETTINGS.embedding_backend
        self.documents: list[Document] = []
        self.backend_name = "tfidf"

        self.tfidf_vectorizer: TfidfVectorizer | None = None
        self.tfidf_matrix: np.ndarray | None = None

        self._dense_model = None
        self._dense_matrix: np.ndarray | None = None

    def build(self, documents: list[Document]) -> None:
        self.documents = documents
        texts = [doc.text for doc in documents]
        if not texts:
            self.tfidf_vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
            self.tfidf_matrix = np.empty((0, 0))
            return

        if self.embedding_backend in {"auto", "dense"}:
            if self._try_build_dense(texts):
                self.backend_name = "dense"
                return

        self.tfidf_vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
        self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(texts)
        self.backend_name = "tfidf"
        logger.info("Vector index built with TF-IDF backend on %s documents", len(documents))

    def search(self, query: str, top_k: int = 5, source_types: set[str] | None = None) -> list[tuple[Document, float]]:
        if not self.documents:
            return []

        ranked_indices: list[int]
        scores: np.ndarray

        if self.backend_name == "dense" and self._dense_model is not None and self._dense_matrix is not None:
            query_vec = self._dense_model.encode([query], normalize_embeddings=True)
            scores = np.matmul(self._dense_matrix, query_vec[0])
            ranked_indices = np.argsort(scores)[::-1].tolist()
        elif self.tfidf_vectorizer is not None and self.tfidf_matrix is not None:
            query_vec = self.tfidf_vectorizer.transform([query])
            scores = cosine_similarity(query_vec, self.tfidf_matrix)[0]
            ranked_indices = np.argsort(scores)[::-1].tolist()
        else:
            return []

        results: list[tuple[Document, float]] = []
        for idx in ranked_indices:
            document = self.documents[idx]
            if source_types and document.source_type not in source_types:
                continue
            score = float(scores[idx])
            results.append((document, score))
            if len(results) >= top_k:
                break
        return results

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "backend_name": self.backend_name,
            "documents": [doc.to_dict() for doc in self.documents],
            "tfidf_vectorizer": self.tfidf_vectorizer,
            "tfidf_matrix": self.tfidf_matrix,
            "dense_matrix": self._dense_matrix,
            "embedding_backend": self.embedding_backend,
            "dense_model_name": SETTINGS.embedding_model,
        }
        with path.open("wb") as fp:
            pickle.dump(payload, fp)

    @classmethod
    def load(cls, path: Path) -> "VectorIndex":
        with path.open("rb") as fp:
            payload = pickle.load(fp)

        index = cls(embedding_backend=payload.get("embedding_backend", "auto"))
        index.backend_name = payload["backend_name"]
        index.documents = [Document(**row) for row in payload["documents"]]
        index.tfidf_vectorizer = payload["tfidf_vectorizer"]
        index.tfidf_matrix = payload["tfidf_matrix"]
        index._dense_matrix = payload.get("dense_matrix")

        if index.backend_name == "dense":
            try:
                from sentence_transformers import SentenceTransformer

                index._dense_model = SentenceTransformer(payload.get("dense_model_name", SETTINGS.embedding_model))
            except Exception as exc:
                logger.warning("Dense model unavailable at load time, falling back to TF-IDF: %s", exc)
                index.backend_name = "tfidf"
        return index

    def _try_build_dense(self, texts: list[str]) -> bool:
        try:
            from sentence_transformers import SentenceTransformer

            self._dense_model = SentenceTransformer(SETTINGS.embedding_model)
            embeddings = self._dense_model.encode(texts, normalize_embeddings=True)
            self._dense_matrix = np.asarray(embeddings)
            logger.info("Vector index built with dense embeddings on %s documents", len(texts))
            return True
        except Exception as exc:
            logger.warning("Dense backend unavailable; using TF-IDF. Reason: %s", exc)
            return False
