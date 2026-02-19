from __future__ import annotations

from campus_assistant.config import PROCESSED_DATA_DIR
from campus_assistant.data_models import Document
from campus_assistant.retrieval.vector_index import VectorIndex
from campus_assistant.utils.io import read_jsonl
from campus_assistant.utils.logging import configure_logging


if __name__ == "__main__":
    configure_logging()
    rows = read_jsonl(PROCESSED_DATA_DIR / "documents.jsonl")
    documents = [Document(**row) for row in rows]
    index = VectorIndex()
    index.build(documents)
    out = PROCESSED_DATA_DIR / "vector_index.pkl"
    index.save(out)
    print(f"Saved index at {out}")
