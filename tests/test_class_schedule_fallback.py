from __future__ import annotations

from campus_assistant.ingestion.class_schedule_ingestor import UMBCClassScheduleIngestor


class _MockErrorResponse:
    def raise_for_status(self) -> None:
        raise RuntimeError("network blocked")


def test_class_schedule_fallback_to_synthetic(monkeypatch) -> None:
    def _mock_get(*args, **kwargs):
        return _MockErrorResponse()

    monkeypatch.setattr("requests.get", _mock_get)

    ingestor = UMBCClassScheduleIngestor(random_seed=1)
    rows = ingestor.fetch(synthetic_size=40)

    assert rows
    assert all(row.is_synthetic for row in rows)
    assert len(rows) <= 40
