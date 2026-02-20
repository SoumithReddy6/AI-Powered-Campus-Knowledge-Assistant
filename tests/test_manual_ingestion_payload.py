from __future__ import annotations

from fastapi import HTTPException

from campus_assistant.web.server import _rows_from_manual_payload


def test_rows_from_manual_payload_accepts_array() -> None:
    rows = _rows_from_manual_payload(
        '[{"term": "Fall 2026", "course_code": "DATA 601", "course_title": "Statistical Learning"}]'
    )
    assert len(rows) == 1
    assert rows[0]["course_code"] == "DATA 601"


def test_rows_from_manual_payload_accepts_records_wrapper() -> None:
    rows = _rows_from_manual_payload(
        '{"records":[{"event_id":"e1","title":"Career Fair","start_time":"2026-03-15"}]}'
    )
    assert len(rows) == 1
    assert rows[0]["event_id"] == "e1"


def test_rows_from_manual_payload_rejects_invalid_shape() -> None:
    try:
        _rows_from_manual_payload('{"bad":"shape"}')
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("Expected HTTPException for invalid payload shape")
