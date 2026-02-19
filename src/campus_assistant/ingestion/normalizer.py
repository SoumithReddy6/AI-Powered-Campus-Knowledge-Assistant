from __future__ import annotations

from campus_assistant.data_models import CalendarEntry, ClassSchedule, Document, EventRecord


def to_documents(
    events: list[EventRecord],
    calendars: list[CalendarEntry],
    schedules: list[ClassSchedule],
) -> list[Document]:
    docs: list[Document] = []

    for event in events:
        docs.append(
            Document(
                doc_id=f"event-{event.event_id}",
                source_type="event",
                title=event.title,
                text=(
                    f"Event: {event.title}\n"
                    f"When: {event.start_time} - {event.end_time}\n"
                    f"Where: {event.location}\n"
                    f"Description: {event.description}"
                ),
                metadata={"url": event.url, "location": event.location, "start_time": event.start_time},
            )
        )

    for entry in calendars:
        docs.append(
            Document(
                doc_id=f"calendar-{entry.entry_id}",
                source_type="calendar",
                title=f"{entry.term}: {entry.date_text}" if entry.date_text else entry.term,
                text=(
                    f"Academic Calendar Term: {entry.term}\n"
                    f"Date: {entry.date_text}\n"
                    f"Detail: {entry.detail}"
                ),
                metadata={"term": entry.term, "source_url": entry.source_url},
            )
        )

    for cls in schedules:
        docs.append(
            Document(
                doc_id=f"class-{cls.class_id}",
                source_type="class_schedule",
                title=f"{cls.course_code} - {cls.course_title}",
                text=(
                    f"Course: {cls.course_code} {cls.course_title}\n"
                    f"Section: {cls.section}\n"
                    f"Term: {cls.term}\n"
                    f"Instructor: {cls.instructor}\n"
                    f"Meeting: {cls.meeting_days} {cls.start_time}-{cls.end_time}\n"
                    f"Location: {cls.building} {cls.room}\n"
                    f"Modality: {cls.modality}"
                ),
                metadata={
                    "course_code": cls.course_code,
                    "term": cls.term,
                    "instructor": cls.instructor,
                    "building": cls.building,
                    "room": cls.room,
                    "is_synthetic": cls.is_synthetic,
                },
            )
        )

    return docs
