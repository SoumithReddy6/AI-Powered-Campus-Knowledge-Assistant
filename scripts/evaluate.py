from __future__ import annotations

import json

from campus_assistant.config import EVAL_DATA_DIR, PROCESSED_DATA_DIR
from campus_assistant.evaluation.benchmark import BenchmarkRunner
from campus_assistant.retrieval.rag_pipeline import RAGPipeline
from campus_assistant.retrieval.vector_index import VectorIndex


if __name__ == "__main__":
    index = VectorIndex.load(PROCESSED_DATA_DIR / "vector_index.pkl")
    rag = RAGPipeline(index)
    report = BenchmarkRunner(rag).run(
        qa_path=EVAL_DATA_DIR / "qa_gold.json",
        output_path=PROCESSED_DATA_DIR / "evaluation_report.json",
    )
    print(json.dumps(report, indent=2))
