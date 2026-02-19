from __future__ import annotations

import argparse
import json
from pathlib import Path

from campus_assistant.config import EVAL_DATA_DIR, PROCESSED_DATA_DIR, ensure_directories
from campus_assistant.utils.logging import configure_logging


def build_index(index_path: Path) -> None:
    from campus_assistant.data_models import Document
    from campus_assistant.retrieval.vector_index import VectorIndex
    from campus_assistant.utils.io import read_jsonl

    rows = read_jsonl(PROCESSED_DATA_DIR / "documents.jsonl")
    documents = []

    for row in rows:
        documents.append(Document(**row))

    index = VectorIndex()
    index.build(documents)
    index.save(index_path)


def run_chat(index_path: Path) -> None:
    from campus_assistant.retrieval.rag_pipeline import RAGPipeline
    from campus_assistant.retrieval.vector_index import VectorIndex

    index = VectorIndex.load(index_path)
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


def run_eval(index_path: Path, qa_path: Path, out_path: Path) -> None:
    from campus_assistant.evaluation.benchmark import BenchmarkRunner
    from campus_assistant.retrieval.rag_pipeline import RAGPipeline
    from campus_assistant.retrieval.vector_index import VectorIndex

    index = VectorIndex.load(index_path)
    rag = RAGPipeline(index)
    report = BenchmarkRunner(rag).run(qa_path=qa_path, output_path=out_path)
    print(json.dumps(report, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="UMBC Campus Knowledge Assistant")
    parser.add_argument("command", choices=["ingest", "build-index", "chat", "evaluate"])
    parser.add_argument("--index-path", default=str(PROCESSED_DATA_DIR / "vector_index.pkl"))
    parser.add_argument("--synthetic-size", type=int, default=120)
    parser.add_argument("--qa-path", default=str(EVAL_DATA_DIR / "qa_gold.json"))
    parser.add_argument("--report-path", default=str(PROCESSED_DATA_DIR / "evaluation_report.json"))
    args = parser.parse_args()

    configure_logging()
    ensure_directories()

    index_path = Path(args.index_path)

    if args.command == "ingest":
        from campus_assistant.ingestion.pipeline import IngestionPipeline

        summary = IngestionPipeline().run(synthetic_size=args.synthetic_size)
        print(json.dumps(summary, indent=2))
    elif args.command == "build-index":
        build_index(index_path=index_path)
        print(f"Index saved at {index_path}")
    elif args.command == "chat":
        run_chat(index_path=index_path)
    elif args.command == "evaluate":
        run_eval(
            index_path=index_path,
            qa_path=Path(args.qa_path),
            out_path=Path(args.report_path),
        )


if __name__ == "__main__":
    main()
