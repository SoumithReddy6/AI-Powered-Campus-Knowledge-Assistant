from __future__ import annotations

import logging

from campus_assistant.config import PROCESSED_DATA_DIR, RAW_DATA_DIR, ensure_directories
from campus_assistant.data_models import CalendarEntry, ClassSchedule, Document, EventRecord
from campus_assistant.ingestion.calendar_ingestor import UMBCAcademicCalendarIngestor
from campus_assistant.ingestion.class_schedule_ingestor import UMBCClassScheduleIngestor
from campus_assistant.ingestion.events_ingestor import UMBCEventsIngestor
from campus_assistant.ingestion.normalizer import to_documents
from campus_assistant.utils.io import write_csv, write_json, write_jsonl

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(self) -> None:
        self.events_ingestor = UMBCEventsIngestor()
        self.calendar_ingestor = UMBCAcademicCalendarIngestor()
        self.schedule_ingestor = UMBCClassScheduleIngestor()

    def run(self, synthetic_size: int = 120) -> dict[str, int]:
        ensure_directories()

        events = self.events_ingestor.fetch()
        calendars = self.calendar_ingestor.fetch()
        schedules = self.schedule_ingestor.fetch(synthetic_size=synthetic_size)
        documents = to_documents(events, calendars, schedules)

        self._persist_raw(events, calendars, schedules)
        self._persist_processed(documents)

        summary = {
            "events": len(events),
            "calendar_entries": len(calendars),
            "class_schedules": len(schedules),
            "documents": len(documents),
            "synthetic_class_schedules": sum(1 for row in schedules if row.is_synthetic),
        }
        logger.info("Ingestion summary: %s", summary)
        return summary

    @staticmethod
    def _persist_raw(
        events: list[EventRecord],
        calendars: list[CalendarEntry],
        schedules: list[ClassSchedule],
    ) -> None:
        write_jsonl(RAW_DATA_DIR / "events.jsonl", [item.to_dict() for item in events])
        write_jsonl(RAW_DATA_DIR / "academic_calendars.jsonl", [item.to_dict() for item in calendars])
        write_jsonl(RAW_DATA_DIR / "class_schedules.jsonl", [item.to_dict() for item in schedules])

        write_csv(RAW_DATA_DIR / "class_schedules.csv", [item.to_dict() for item in schedules])

    @staticmethod
    def _persist_processed(documents: list[Document]) -> None:
        rows = [doc.to_dict() for doc in documents]
        write_jsonl(PROCESSED_DATA_DIR / "documents.jsonl", rows)
        write_json(PROCESSED_DATA_DIR / "documents.json", rows)
