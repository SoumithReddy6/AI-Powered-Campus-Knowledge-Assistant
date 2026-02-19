from __future__ import annotations

from campus_assistant.config import PROCESSED_DATA_DIR
from campus_assistant.retrieval.rag_pipeline import RAGPipeline
from campus_assistant.retrieval.vector_index import VectorIndex


if __name__ == "__main__":
    index = VectorIndex.load(PROCESSED_DATA_DIR / "vector_index.pkl")
    rag = RAGPipeline(index)
    print("UMBC Campus Assistant (type 'exit' to quit)")
    while True:
        query = input("\nYou: ").strip()
        if query.lower() in {"exit", "quit"}:
            break
        result = rag.answer(query)
        print(f"\nAssistant: {result.answer}")
        print(f"Intent: {result.intent} | Latency: {result.latency_ms:.2f} ms")
        if result.sources:
            print("Sources:")
            for src in result.sources[:3]:
                print(f"- {src['doc_id']} ({src['source_type']}, score={src['score']})")
