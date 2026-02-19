from __future__ import annotations

import statistics
from pathlib import Path

from campus_assistant.data_models import QueryResult
from campus_assistant.evaluation.metrics import (
    classification_metrics,
    hit_rate_at_k,
    reciprocal_rank,
    token_overlap_correctness,
)
from campus_assistant.retrieval.rag_pipeline import RAGPipeline
from campus_assistant.utils.io import read_json, write_json


class BenchmarkRunner:
    def __init__(self, rag: RAGPipeline) -> None:
        self.rag = rag

    def run(self, qa_path: Path, output_path: Path) -> dict:
        qa_rows = read_json(qa_path)

        intent_true: list[str] = []
        intent_pred: list[str] = []
        hit_rates: list[float] = []
        rr_scores: list[float] = []
        correctness_scores: list[float] = []
        latencies: list[float] = []
        details: list[dict] = []

        for row in qa_rows:
            result: QueryResult = self.rag.answer(row["question"])

            intent_true.append(row.get("intent", "general"))
            intent_pred.append(result.intent)
            latencies.append(result.latency_ms)

            ranked = [source["doc_id"] for source in result.sources]
            expected = _resolve_expected_doc_ids(
                expected_doc_ids=row.get("expected_doc_ids", []),
                expected_prefixes=row.get("expected_doc_prefixes", []),
                ranked_doc_ids=ranked,
                expected_source_types=row.get("expected_source_types", []),
                ranked_sources=result.sources,
            )
            hit_rates.append(hit_rate_at_k(expected, ranked, k=5))
            rr_scores.append(reciprocal_rank(expected, ranked))

            ref_answer = row.get("reference_answer", "")
            correctness_scores.append(token_overlap_correctness(ref_answer, result.answer))

            details.append(
                {
                    "question": row["question"],
                    "predicted_intent": result.intent,
                    "latency_ms": result.latency_ms,
                    "sources": ranked,
                    "answer": result.answer,
                }
            )

        report = {
            "intent": classification_metrics(intent_true, intent_pred),
            "retrieval": {
                "hit_rate_at_5": statistics.mean(hit_rates) if hit_rates else 0.0,
                "mrr": statistics.mean(rr_scores) if rr_scores else 0.0,
            },
            "response_quality": {
                "token_overlap_correctness": statistics.mean(correctness_scores) if correctness_scores else 0.0,
                "avg_latency_ms": statistics.mean(latencies) if latencies else 0.0,
                "p95_latency_ms": _percentile(latencies, 95),
            },
            "samples": details,
        }
        write_json(output_path, report)
        return report


def _resolve_expected_doc_ids(
    expected_doc_ids: list[str],
    expected_prefixes: list[str],
    ranked_doc_ids: list[str],
    expected_source_types: list[str],
    ranked_sources: list[dict],
) -> list[str]:
    if expected_doc_ids:
        return expected_doc_ids

    resolved: set[str] = set()

    if expected_prefixes:
        for doc_id in ranked_doc_ids:
            if any(doc_id.startswith(prefix) for prefix in expected_prefixes):
                resolved.add(doc_id)

    if expected_source_types:
        allowed = set(expected_source_types)
        for src in ranked_sources:
            if src.get("source_type") in allowed:
                resolved.add(src["doc_id"])

    return list(resolved)


def _percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int((p / 100) * (len(ordered) - 1))
    return ordered[idx]
