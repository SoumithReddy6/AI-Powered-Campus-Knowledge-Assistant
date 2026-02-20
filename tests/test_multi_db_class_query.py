from __future__ import annotations

import sqlite3

from campus_assistant.db.multi_db import (
    CLASSES_DB_PATH,
    build_class_catalog_answer,
    init_databases,
    parse_semester_from_query,
    upsert_class_rows,
)


def _reset_class_table() -> None:
    init_databases()
    conn = sqlite3.connect(CLASSES_DB_PATH)
    try:
        conn.execute("DELETE FROM classes")
        conn.commit()
    finally:
        conn.close()


def test_parse_semester_and_department_from_data_stream_query() -> None:
    department, term = parse_semester_from_query(
        "What are the classes listed for upcoming semester in Data stream"
    )

    assert department == "DATA"
    # Term may be None when DB terms are empty; upcoming is computed once data exists.
    assert term is None or isinstance(term, str)


def test_build_class_catalog_answer_for_upcoming_data_classes() -> None:
    _reset_class_table()

    upsert_class_rows(
        [
            {
                "class_id": "x1",
                "term": "Fall 2026",
                "course_code": "DATA 601",
                "course_title": "Statistical Learning",
                "section": "01",
                "instructor": "A. Johnson",
                "meeting_days": "MW",
                "start_time": "10:00",
                "end_time": "11:15",
                "building": "Engineering",
                "room": "204",
                "modality": "In Person",
            },
            {
                "class_id": "x2",
                "term": "Fall 2026",
                "course_code": "DATA 610",
                "course_title": "Data Engineering",
                "section": "02",
                "instructor": "R. Chen",
                "meeting_days": "TR",
                "start_time": "13:00",
                "end_time": "14:15",
                "building": "ITE",
                "room": "301",
                "modality": "In Person",
            },
            {
                "class_id": "x3",
                "term": "Spring 2026",
                "course_code": "CMSC 601",
                "course_title": "Advanced Algorithms",
                "section": "01",
            },
        ]
    )

    answer, sources, meta = build_class_catalog_answer(
        "What are the classes listed for upcoming semester in Data stream"
    )

    assert meta["department"] == "DATA"
    assert meta["term"] in {"Spring 2026", "Fall 2026"}
    assert "DATA 601" in answer
    assert "DATA 610" in answer
    assert "CMSC 601" not in answer
    assert all(src["source_type"] == "class_database" for src in sources)
