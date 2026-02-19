from __future__ import annotations

from collections.abc import Sequence

from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score


def classification_metrics(y_true: Sequence[str], y_pred: Sequence[str]) -> dict[str, float]:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
    }


def hit_rate_at_k(expected_doc_ids: list[str], ranked_doc_ids: list[str], k: int = 5) -> float:
    top = ranked_doc_ids[:k]
    return 1.0 if any(doc_id in top for doc_id in expected_doc_ids) else 0.0


def reciprocal_rank(expected_doc_ids: list[str], ranked_doc_ids: list[str]) -> float:
    for idx, doc_id in enumerate(ranked_doc_ids, start=1):
        if doc_id in expected_doc_ids:
            return 1.0 / idx
    return 0.0


def token_overlap_correctness(reference_answer: str, predicted_answer: str) -> float:
    ref = {token.lower() for token in reference_answer.split() if token.strip()}
    pred = {token.lower() for token in predicted_answer.split() if token.strip()}
    if not ref:
        return 0.0
    return len(ref.intersection(pred)) / len(ref)
