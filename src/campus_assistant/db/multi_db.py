from __future__ import annotations

import csv
import io
import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from campus_assistant.config import DATA_DIR

DB_DIR = DATA_DIR / "db"
EVENTS_DB_PATH = DB_DIR / "events.db"
CALENDARS_DB_PATH = DB_DIR / "calendars.db"
CLASSES_DB_PATH = DB_DIR / "classes.db"

TERM_PATTERN = re.compile(r"\b(spring|summer|fall|winter)\s+(20\d{2})\b", re.IGNORECASE)
COURSE_PREFIX_PATTERN = re.compile(r"\b([A-Z]{2,5})\s?\d{3}[A-Z]?\b")

DEPARTMENT_ALIASES = {
    "data": "DATA",
    "data stream": "DATA",
    "data science": "DATA",
    "computer science": "CMSC",
    "information systems": "IS",
    "math": "MATH",
    "mathematics": "MATH",
    "statistics": "STAT",
    "econ": "ECON",
    "economics": "ECON",
}

SEASON_ORDER = {
    "winter": 1,
    "spring": 2,
    "summer": 3,
    "fall": 4,
}


def init_databases() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)

    with _connect(EVENTS_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                start_time TEXT,
                end_time TEXT,
                location TEXT,
                url TEXT,
                source TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    with _connect(CALENDARS_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS calendars (
                entry_id TEXT PRIMARY KEY,
                term TEXT,
                date_text TEXT,
                detail TEXT,
                source_url TEXT,
                source TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    with _connect(CLASSES_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id TEXT,
                term TEXT NOT NULL,
                department TEXT,
                course_code TEXT NOT NULL,
                course_title TEXT,
                section TEXT,
                instructor TEXT,
                meeting_days TEXT,
                start_time TEXT,
                end_time TEXT,
                building TEXT,
                room TEXT,
                modality TEXT,
                is_synthetic INTEGER DEFAULT 0,
                source TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(term, course_code, section)
            )
            """
        )


def upsert_event_rows(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    with _connect(EVENTS_DB_PATH) as conn:
        for row in rows:
            conn.execute(
                """
                INSERT INTO events (
                    event_id, title, description, start_time, end_time,
                    location, url, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    start_time = excluded.start_time,
                    end_time = excluded.end_time,
                    location = excluded.location,
                    url = excluded.url,
                    source = excluded.source,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    _str(row.get("event_id")),
                    _str(row.get("title")),
                    _str(row.get("description")),
                    _str(row.get("start_time")),
                    _str(row.get("end_time")),
                    _str(row.get("location")),
                    _str(row.get("url")),
                    _str(row.get("source", "umbc_events")),
                ),
            )
        conn.commit()
    return len(rows)


def upsert_calendar_rows(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    with _connect(CALENDARS_DB_PATH) as conn:
        for row in rows:
            conn.execute(
                """
                INSERT INTO calendars (
                    entry_id, term, date_text, detail, source_url, source
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(entry_id) DO UPDATE SET
                    term = excluded.term,
                    date_text = excluded.date_text,
                    detail = excluded.detail,
                    source_url = excluded.source_url,
                    source = excluded.source,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    _str(row.get("entry_id")),
                    _str(row.get("term")),
                    _str(row.get("date_text")),
                    _str(row.get("detail")),
                    _str(row.get("source_url")),
                    _str(row.get("source", "umbc_academic_calendar")),
                ),
            )
        conn.commit()
    return len(rows)


def upsert_class_rows(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    with _connect(CLASSES_DB_PATH) as conn:
        for row in rows:
            course_code = _normalize_course_code(_str(row.get("course_code")))
            term = _str(row.get("term"))
            section = _str(row.get("section") or "01")
            department = _infer_department(course_code)

            conn.execute(
                """
                INSERT INTO classes (
                    class_id, term, department, course_code, course_title,
                    section, instructor, meeting_days, start_time, end_time,
                    building, room, modality, is_synthetic, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(term, course_code, section) DO UPDATE SET
                    class_id = excluded.class_id,
                    department = excluded.department,
                    course_title = excluded.course_title,
                    instructor = excluded.instructor,
                    meeting_days = excluded.meeting_days,
                    start_time = excluded.start_time,
                    end_time = excluded.end_time,
                    building = excluded.building,
                    room = excluded.room,
                    modality = excluded.modality,
                    is_synthetic = excluded.is_synthetic,
                    source = excluded.source,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    _str(row.get("class_id")),
                    term,
                    department,
                    course_code,
                    _str(row.get("course_title")),
                    section,
                    _str(row.get("instructor")),
                    _str(row.get("meeting_days")),
                    _str(row.get("start_time")),
                    _str(row.get("end_time")),
                    _str(row.get("building")),
                    _str(row.get("room")),
                    _str(row.get("modality")),
                    1 if bool(row.get("is_synthetic")) else 0,
                    _str(row.get("source", "umbc_class_schedule")),
                ),
            )
        conn.commit()
    return len(rows)


def fetch_class_records(
    *,
    department: str | None = None,
    term: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    where = []
    params: list[Any] = []

    if department:
        where.append("department = ?")
        params.append(department.upper())
    if term:
        where.append("LOWER(term) = LOWER(?)")
        params.append(term)

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    query = f"""
        SELECT
            class_id, term, department, course_code, course_title, section,
            instructor, meeting_days, start_time, end_time,
            building, room, modality, is_synthetic, source
        FROM classes
        {clause}
        ORDER BY term ASC, course_code ASC, section ASC
        LIMIT ?
    """
    params.append(limit)

    with _connect(CLASSES_DB_PATH) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def fetch_event_records(*, limit: int = 200) -> list[dict[str, Any]]:
    with _connect(EVENTS_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT
                event_id, title, description, start_time, end_time,
                location, url, source, updated_at
            FROM events
            ORDER BY updated_at DESC, start_time ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_calendar_records(*, term: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    where = ""
    params: list[Any] = []
    if term:
        where = "WHERE LOWER(term) = LOWER(?)"
        params.append(term)
    params.append(limit)

    with _connect(CALENDARS_DB_PATH) as conn:
        rows = conn.execute(
            f"""
            SELECT
                entry_id, term, date_text, detail, source_url,
                source, updated_at
            FROM calendars
            {where}
            ORDER BY updated_at DESC, term ASC, date_text ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_event_promotions(*, limit: int = 8) -> list[dict[str, Any]]:
    with _connect(EVENTS_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT
                event_id, title, description, start_time, end_time,
                location, url, source
            FROM events
            WHERE TRIM(title) != ''
            ORDER BY updated_at DESC, start_time ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_distinct_terms() -> list[str]:
    with _connect(CLASSES_DB_PATH) as conn:
        rows = conn.execute("SELECT DISTINCT term FROM classes WHERE term != ''").fetchall()
    terms = [row["term"] for row in rows if row["term"]]
    return sorted(terms, key=_term_sort_key)


def fetch_upcoming_term() -> str | None:
    terms = fetch_distinct_terms()
    if not terms:
        return None

    current_key = _current_term_key()
    keys = [(term, _term_sort_key(term)) for term in terms]
    future = [pair for pair in keys if pair[1] > current_key]
    if future:
        return min(future, key=lambda x: x[1])[0]
    current_or_future = [pair for pair in keys if pair[1] >= current_key]
    if current_or_future:
        return min(current_or_future, key=lambda x: x[1])[0]
    return min(keys, key=lambda x: x[1])[0]


def parse_semester_from_query(query: str) -> tuple[str | None, str | None]:
    lowered = query.lower()

    department = None
    for phrase, code in DEPARTMENT_ALIASES.items():
        if phrase in lowered:
            department = code
            break

    if department is None:
        course_match = COURSE_PREFIX_PATTERN.search(query.upper())
        if course_match:
            department = _infer_department(course_match.group(0))

    explicit_term = TERM_PATTERN.search(query)
    if explicit_term:
        term = f"{explicit_term.group(1).title()} {explicit_term.group(2)}"
        return department, term

    if any(token in lowered for token in ["upcoming semester", "next semester", "next term", "upcoming term"]):
        return department, fetch_upcoming_term()

    if any(token in lowered for token in ["current semester", "this semester", "current term", "this term"]):
        term = _find_current_term_from_db()
        return department, term or fetch_upcoming_term()

    return department, None


def build_class_catalog_answer(query: str, limit: int = 60) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    department, term = parse_semester_from_query(query)

    rows = fetch_class_records(department=department, term=term, limit=limit)
    if not rows and term:
        # If requested term has no rows, relax by term and keep department filter.
        rows = fetch_class_records(department=department, term=None, limit=limit)

    if not rows:
        return (
            "I could not find class catalog records yet. Ask the database admin to upload class data, "
            "or run ingestion first.",
            [],
            {"department": department, "term": term},
        )

    # If term wasn't explicit, pick most relevant upcoming term for clearer listing.
    effective_term = term or _best_term_for_rows(rows)
    if effective_term:
        rows = [row for row in rows if row.get("term", "").lower() == effective_term.lower()] or rows

    title_bits: list[str] = []
    if department:
        title_bits.append(f"{department} courses")
    else:
        title_bits.append("courses")
    if effective_term:
        title_bits.append(f"for {effective_term}")

    answer_lines = [f"Here are the {', '.join(title_bits)}:"]
    for idx, row in enumerate(rows[:25], start=1):
        meeting = " ".join(part for part in [row.get("meeting_days"), _time_range(row)] if part).strip()
        location = " ".join(part for part in [row.get("building"), row.get("room")] if part).strip()
        details = [f"Section {row.get('section', '01')}"]
        if row.get("instructor"):
            details.append(str(row["instructor"]))
        if meeting:
            details.append(meeting)
        if location:
            details.append(location)

        answer_lines.append(
            f"{idx}. {row.get('course_code', '')} - {row.get('course_title', 'Untitled')} ({' | '.join(details)})"
        )

    sources = [
        {
            "doc_id": f"classdb-{row.get('term', '')}-{row.get('course_code', '')}-{row.get('section', '')}",
            "title": f"{row.get('course_code', '')} - {row.get('course_title', 'Untitled')}",
            "source_type": "class_database",
            "score": 1.0,
            "metadata": {
                "term": row.get("term"),
                "department": row.get("department"),
                "section": row.get("section"),
                "instructor": row.get("instructor"),
                "meeting_days": row.get("meeting_days"),
                "start_time": row.get("start_time"),
                "end_time": row.get("end_time"),
                "building": row.get("building"),
                "room": row.get("room"),
                "is_synthetic": bool(row.get("is_synthetic")),
                "source": row.get("source"),
            },
        }
        for row in rows[:25]
    ]

    meta = {
        "department": department,
        "term": effective_term,
        "count": len(rows),
    }

    return "\n".join(answer_lines), sources, meta


def class_records_from_csv_text(csv_text: str) -> list[dict[str, Any]]:
    stream = io.StringIO(csv_text)
    reader = csv.DictReader(stream)

    required = {"term", "course_code", "course_title"}
    missing = [col for col in required if col not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(
            "CSV is missing required columns: " + ", ".join(sorted(missing))
        )

    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(reader):
        if not row:
            continue
        if not str(row.get("term", "")).strip() or not str(row.get("course_code", "")).strip():
            continue

        rows.append(
            {
                "class_id": row.get("class_id") or f"admin-{idx}",
                "term": row.get("term", "").strip(),
                "course_code": _normalize_course_code(row.get("course_code", "")),
                "course_title": row.get("course_title", "").strip(),
                "section": (row.get("section") or "01").strip(),
                "instructor": (row.get("instructor") or "TBA").strip(),
                "meeting_days": (row.get("meeting_days") or "").strip(),
                "start_time": (row.get("start_time") or "").strip(),
                "end_time": (row.get("end_time") or "").strip(),
                "building": (row.get("building") or "").strip(),
                "room": (row.get("room") or "").strip(),
                "modality": (row.get("modality") or "In Person").strip(),
                "is_synthetic": str(row.get("is_synthetic", "0")).strip().lower() in {"1", "true", "yes"},
                "source": row.get("source") or "admin_upload",
            }
        )

    return rows


def get_db_counts() -> dict[str, Any]:
    with _connect(EVENTS_DB_PATH) as conn:
        events_count = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]

    with _connect(CALENDARS_DB_PATH) as conn:
        calendars_count = conn.execute("SELECT COUNT(*) AS c FROM calendars").fetchone()["c"]

    with _connect(CLASSES_DB_PATH) as conn:
        classes_count = conn.execute("SELECT COUNT(*) AS c FROM classes").fetchone()["c"]

    terms = fetch_distinct_terms()

    return {
        "events": int(events_count),
        "calendars": int(calendars_count),
        "classes": int(classes_count),
        "class_terms": terms,
        "upcoming_term": fetch_upcoming_term(),
    }


def _find_current_term_from_db() -> str | None:
    terms = fetch_distinct_terms()
    if not terms:
        return None
    current_key = _current_term_key()
    ranked = [(term, _term_sort_key(term)) for term in terms]

    # closest term to "now"
    return min(ranked, key=lambda pair: abs(pair[1] - current_key))[0]


def _best_term_for_rows(rows: list[dict[str, Any]]) -> str | None:
    terms = sorted({str(row.get("term", "")) for row in rows if row.get("term")}, key=_term_sort_key)
    if not terms:
        return None
    upcoming = fetch_upcoming_term()
    if upcoming and upcoming in terms:
        return upcoming
    return terms[0]


def _time_range(row: dict[str, Any]) -> str:
    start = (row.get("start_time") or "").strip()
    end = (row.get("end_time") or "").strip()
    if start and end:
        return f"{start}-{end}"
    return start or end


def _infer_department(course_code: str) -> str:
    match = re.match(r"^\s*([A-Za-z]{2,5})\s*\d", course_code)
    if match:
        return match.group(1).upper()
    alpha = re.match(r"^\s*([A-Za-z]{2,5})\b", course_code)
    if alpha:
        return alpha.group(1).upper()
    return ""


def _normalize_course_code(course_code: str) -> str:
    match = re.match(r"^\s*([A-Za-z]{2,5})\s*-?\s*(\d{3}[A-Za-z]?)\s*$", str(course_code))
    if match:
        return f"{match.group(1).upper()} {match.group(2).upper()}"
    return str(course_code).strip().upper()


def _term_sort_key(term: str) -> int:
    match = TERM_PATTERN.search(term or "")
    if not match:
        return 10_000_000
    season = match.group(1).lower()
    year = int(match.group(2))
    season_rank = SEASON_ORDER.get(season, 9)
    return year * 10 + season_rank


def _current_term_key() -> int:
    today = date.today()
    year = today.year
    month = today.month

    if month in {1}:
        season = "winter"
    elif month in {2, 3, 4, 5}:
        season = "spring"
    elif month in {6, 7, 8}:
        season = "summer"
    else:
        season = "fall"

    return year * 10 + SEASON_ORDER[season]


def _str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn
