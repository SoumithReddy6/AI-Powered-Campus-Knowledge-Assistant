from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class EventRecord:
    event_id: str
    title: str
    description: str
    start_time: str
    end_time: str
    location: str
    url: str
    source: str = "umbc_events"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CalendarEntry:
    entry_id: str
    term: str
    date_text: str
    detail: str
    source_url: str
    source: str = "umbc_academic_calendar"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClassSchedule:
    class_id: str
    term: str
    course_code: str
    course_title: str
    section: str
    instructor: str
    meeting_days: str
    start_time: str
    end_time: str
    building: str
    room: str
    modality: str
    is_synthetic: bool = False
    source: str = "umbc_class_schedule"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Document:
    doc_id: str
    source_type: str
    title: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QueryResult:
    query: str
    answer: str
    intent: str
    entities: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    latency_ms: float
    normalized_query: str | None = None
    correction_applied: bool = False
    corrections: list[dict[str, str]] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
