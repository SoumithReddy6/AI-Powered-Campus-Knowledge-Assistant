from __future__ import annotations

import logging
import random
from typing import Iterable

import requests
from bs4 import BeautifulSoup

from campus_assistant.config import SETTINGS
from campus_assistant.data_models import ClassSchedule

logger = logging.getLogger(__name__)


class UMBCClassScheduleIngestor:
    def __init__(self, random_seed: int = 42) -> None:
        self.headers = {"User-Agent": SETTINGS.user_agent}
        self.random = random.Random(random_seed)

    def fetch(self, synthetic_size: int = 120) -> list[ClassSchedule]:
        real_records = self._fetch_public_schedule()
        if real_records:
            logger.info("Loaded %s class schedule records from public source", len(real_records))
            return real_records
        logger.info("Class schedule public source unavailable. Generating synthetic fallback.")
        return self._generate_synthetic_schedule(count=synthetic_size)

    def _fetch_public_schedule(self) -> list[ClassSchedule]:
        try:
            response = requests.get(
                SETTINGS.umbc_class_search_url,
                headers=self.headers,
                timeout=SETTINGS.request_timeout_seconds,
                allow_redirects=True,
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning("Class search endpoint unavailable: %s", exc)
            return []

        body_lower = response.text.lower()
        if "single sign-on" in body_lower or "authentication required" in body_lower:
            return []
        if "login" in body_lower and "class" not in body_lower:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        tables = soup.select("table")
        if not tables:
            return []

        rows: list[ClassSchedule] = []
        for idx, tr in enumerate(soup.select("tr")):
            cells = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if len(cells) < 8:
                continue

            course_code = cells[0]
            if not any(ch.isdigit() for ch in course_code):
                continue

            rows.append(
                ClassSchedule(
                    class_id=f"real-{idx}",
                    term=cells[1] if len(cells) > 1 else "Unknown term",
                    course_code=course_code,
                    course_title=cells[2] if len(cells) > 2 else "",
                    section=cells[3] if len(cells) > 3 else "",
                    instructor=cells[4] if len(cells) > 4 else "TBA",
                    meeting_days=cells[5] if len(cells) > 5 else "",
                    start_time=cells[6] if len(cells) > 6 else "",
                    end_time=cells[7] if len(cells) > 7 else "",
                    building=cells[8] if len(cells) > 8 else "",
                    room=cells[9] if len(cells) > 9 else "",
                    modality=cells[10] if len(cells) > 10 else "In Person",
                    is_synthetic=False,
                )
            )

        return rows[:1000]

    def _generate_synthetic_schedule(self, count: int) -> list[ClassSchedule]:
        terms = ["Spring 2026", "Summer 2026", "Fall 2026"]
        departments = {
            "CMSC": [
                "Applied Machine Learning",
                "Data Mining",
                "Advanced Algorithms",
                "Information Retrieval",
            ],
            "DATA": [
                "Statistical Learning",
                "Data Engineering",
                "Responsible AI",
                "Optimization for Analytics",
            ],
            "IS": [
                "Natural Language Processing",
                "Human-Centered AI Systems",
                "Knowledge Management",
                "Cloud Platforms for Data",
            ],
            "MATH": [
                "Linear Algebra for ML",
                "Probability Models",
                "Numerical Methods",
                "Stochastic Processes",
            ],
        }
        instructors = [
            "A. Johnson",
            "M. Patel",
            "R. Chen",
            "L. Thompson",
            "S. Ibrahim",
            "K. O'Neill",
            "D. Garcia",
            "E. Robinson",
        ]
        buildings = [
            "Engineering",
            "ITE",
            "Mathematics/Psychology",
            "Sherman Hall",
            "Public Policy",
            "Performing Arts & Humanities",
            "University Center",
        ]
        rooms = ["101", "105", "204", "220", "301", "315", "410", "450"]
        day_options = ["MW", "TR", "MWF", "F", "Online"]
        time_slots = [
            ("08:30", "09:45"),
            ("10:00", "11:15"),
            ("11:30", "12:45"),
            ("13:00", "14:15"),
            ("14:30", "15:45"),
            ("16:00", "17:15"),
            ("18:00", "20:30"),
        ]

        course_numbers = list(range(500, 790))
        used = set()
        synthetic: list[ClassSchedule] = []

        for idx in range(count):
            dept = self.random.choice(list(departments.keys()))
            title = self.random.choice(departments[dept])
            course_number = self.random.choice(course_numbers)
            section = f"0{self.random.randint(1, 6)}"
            term = self.random.choice(terms)
            modality = self.random.choice(["In Person", "Hybrid", "Online"])
            days = self.random.choice(day_options)
            start, end = self.random.choice(time_slots)
            building = self.random.choice(buildings)
            room = self.random.choice(rooms)
            instructor = self.random.choice(instructors)

            dedupe_key = (dept, course_number, section, term)
            if dedupe_key in used:
                continue
            used.add(dedupe_key)

            if modality == "Online":
                building = "Online"
                room = "Virtual"
                days = "Async"
                start, end = ("", "")

            synthetic.append(
                ClassSchedule(
                    class_id=f"synthetic-{idx}",
                    term=term,
                    course_code=f"{dept} {course_number}",
                    course_title=title,
                    section=section,
                    instructor=instructor,
                    meeting_days=days,
                    start_time=start,
                    end_time=end,
                    building=building,
                    room=room,
                    modality=modality,
                    is_synthetic=True,
                )
            )

        return synthetic


def iter_schedules_by_term(rows: Iterable[ClassSchedule], term: str) -> list[ClassSchedule]:
    return [row for row in rows if row.term.lower() == term.lower()]
