from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass
class ExtractedEntity:
    text: str
    label: str
    start: int
    end: int
    confidence: float

    def to_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


class CampusEntityExtractor:
    BUILDINGS = [
        "Engineering",
        "ITE",
        "Sherman Hall",
        "University Center",
        "Mathematics/Psychology",
        "Public Policy",
        "Sondheim Hall",
        "Library",
    ]
    SERVICES = [
        "financial aid",
        "registrar",
        "library",
        "career center",
        "dining",
        "transit",
        "commons",
    ]

    # Restrict to plausible department prefixes to reduce false positives.
    COURSE_DEPARTMENTS = {
        "AFST",
        "ANTH",
        "ART",
        "BIOL",
        "CHEM",
        "CMSC",
        "DATA",
        "ECON",
        "EDUC",
        "ENGL",
        "GWST",
        "HIST",
        "IS",
        "MATH",
        "ME",
        "PHYS",
        "POLI",
        "PSYC",
        "SOCY",
        "STAT",
    }
    COURSE_PATTERN = re.compile(r"\b([A-Z]{2,5})\s?(\d{3}[A-Z]?)\b")
    ROOM_PATTERN = re.compile(r"\b(?:room|rm)\s*([A-Z]?\d{2,4})\b", re.IGNORECASE)

    def extract(self, query: str) -> list[ExtractedEntity]:
        entities: list[ExtractedEntity] = []
        lowered = query.lower()

        for building in self.BUILDINGS:
            idx = lowered.find(building.lower())
            if idx >= 0:
                entities.append(
                    ExtractedEntity(
                        text=query[idx : idx + len(building)],
                        label="BUILDING",
                        start=idx,
                        end=idx + len(building),
                        confidence=0.95,
                    )
                )

        for service in self.SERVICES:
            idx = lowered.find(service.lower())
            if idx >= 0:
                entities.append(
                    ExtractedEntity(
                        text=query[idx : idx + len(service)],
                        label="SERVICE",
                        start=idx,
                        end=idx + len(service),
                        confidence=0.9,
                    )
                )

        for match in self.COURSE_PATTERN.finditer(query.upper()):
            dept = match.group(1)
            if dept not in self.COURSE_DEPARTMENTS:
                continue
            entities.append(
                ExtractedEntity(
                    text=match.group(0),
                    label="COURSE_CODE",
                    start=match.start(),
                    end=match.end(),
                    confidence=0.98,
                )
            )

        for match in self.ROOM_PATTERN.finditer(query):
            room_text = match.group(1)
            if len(room_text.strip()) < 3:
                continue
            entities.append(
                ExtractedEntity(
                    text=room_text,
                    label="ROOM",
                    start=match.start(1),
                    end=match.end(1),
                    confidence=0.82,
                )
            )

        # Deduplicate by span + label.
        unique: dict[tuple[int, int, str], ExtractedEntity] = {}
        for entity in entities:
            unique[(entity.start, entity.end, entity.label)] = entity

        return list(unique.values())
