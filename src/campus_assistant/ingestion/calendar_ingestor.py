from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from campus_assistant.config import SETTINGS
from campus_assistant.data_models import CalendarEntry

logger = logging.getLogger(__name__)

_DATE_PATTERN = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,\s*\d{4})?\b",
    flags=re.IGNORECASE,
)


class UMBCAcademicCalendarIngestor:
    def __init__(self) -> None:
        self.headers = {"User-Agent": SETTINGS.user_agent}

    def fetch(self) -> list[CalendarEntry]:
        try:
            response = requests.get(
                SETTINGS.umbc_academic_calendar_url,
                headers=self.headers,
                timeout=SETTINGS.request_timeout_seconds,
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning("UMBC calendar page unavailable: %s", exc)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        links = self._candidate_links(soup)
        entries: list[CalendarEntry] = []

        for idx, (term_label, link) in enumerate(links):
            term_entries = self._extract_term_entries(term_label, link)
            if term_entries:
                entries.extend(term_entries)
                continue
            entries.append(
                CalendarEntry(
                    entry_id=f"calendar-{idx}",
                    term=term_label,
                    date_text="",
                    detail=f"Calendar link: {link}",
                    source_url=link,
                )
            )

        logger.info("Loaded %s academic calendar entries", len(entries))
        return entries

    def _candidate_links(self, soup: BeautifulSoup) -> list[tuple[str, str]]:
        links: list[tuple[str, str]] = []
        for anchor in soup.select("a[href]"):
            text = anchor.get_text(" ", strip=True)
            href = anchor.get("href", "").strip()
            if not href:
                continue
            lowered = text.lower()
            if not any(term in lowered for term in ["spring", "summer", "fall", "winter"]):
                continue
            if "date" not in lowered and "deadline" not in lowered:
                continue
            full_url = urljoin(SETTINGS.umbc_academic_calendar_url, href)
            links.append((text, full_url))

        unique: dict[str, str] = {}
        for label, link in links:
            unique[link] = label
        return [(label, link) for link, label in unique.items()]

    def _extract_term_entries(self, term: str, url: str) -> list[CalendarEntry]:
        try:
            response = requests.get(url, headers=self.headers, timeout=SETTINGS.request_timeout_seconds)
            response.raise_for_status()
        except Exception as exc:
            logger.warning("Calendar term page unavailable (%s): %s", url, exc)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        lines = self._interesting_lines(soup.get_text("\n", strip=True))
        entries: list[CalendarEntry] = []
        for idx, line in enumerate(lines):
            date_match = _DATE_PATTERN.search(line)
            entries.append(
                CalendarEntry(
                    entry_id=f"{_slug(term)}-{idx}",
                    term=term,
                    date_text=date_match.group(0) if date_match else "",
                    detail=line,
                    source_url=url,
                )
            )
        return entries

    @staticmethod
    def _interesting_lines(raw_text: str) -> list[str]:
        out: list[str] = []
        for line in raw_text.splitlines():
            line = " ".join(line.split())
            if len(line) < 20:
                continue
            has_date = bool(_DATE_PATTERN.search(line))
            has_deadline = any(token in line.lower() for token in ["deadline", "registration", "exam", "withdraw", "semester"])
            if has_date or has_deadline:
                out.append(line)
        return out[:300]


def _slug(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum() or ch == " ").replace(" ", "-")[:42]
