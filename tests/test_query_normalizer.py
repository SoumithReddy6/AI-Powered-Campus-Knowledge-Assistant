from __future__ import annotations

from campus_assistant.nlp.query_normalizer import QueryNormalizer


def test_query_normalizer_corrects_common_typos() -> None:
    normalizer = QueryNormalizer()
    normalized = normalizer.normalize("wen is sprng 2026 add drop dline")

    assert normalized.applied is True
    assert "when" in normalized.corrected.lower()
    assert "spring" in normalized.corrected.lower()
    assert "deadline" in normalized.corrected.lower()


def test_query_normalizer_keeps_course_codes() -> None:
    normalizer = QueryNormalizer()
    normalized = normalizer.normalize("who teaches cmsc601")

    assert "CMSC 601" in normalized.corrected
