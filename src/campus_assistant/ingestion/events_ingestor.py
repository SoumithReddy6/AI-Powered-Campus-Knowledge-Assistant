from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from campus_assistant.config import SETTINGS
from campus_assistant.data_models import EventRecord

logger = logging.getLogger(__name__)


class UMBCEventsIngestor:
    def __init__(self) -> None:
        self.headers = {"User-Agent": SETTINGS.user_agent}

    def fetch(self) -> list[EventRecord]:
        records = self._fetch_from_api_xml()
        if records:
            return records
        return self._fetch_from_html()

    def _fetch_from_api_xml(self) -> list[EventRecord]:
        try:
            response = requests.get(
                SETTINGS.umbc_events_api_url,
                headers=self.headers,
                timeout=SETTINGS.request_timeout_seconds,
            )
            response.raise_for_status()
            root = ET.fromstring(response.text)
        except Exception as exc:
            logger.warning("UMBC events XML endpoint unavailable: %s", exc)
            return []

        events: list[EventRecord] = []
        for event_el in root.findall(".//event"):
            raw_id = _first_text(event_el, ["id", "event_id"]) or _stable_id(_first_text(event_el, ["title"]) or "event")
            title = _first_text(event_el, ["title"]) or "Untitled event"
            description = _first_text(event_el, ["description", "summary"]) or ""
            start = _first_text(event_el, ["start_date", "start-time", "start"]) or ""
            end = _first_text(event_el, ["end_date", "end-time", "end"]) or ""
            location = _first_text(event_el, ["location", "where"]) or "UMBC"
            url = _first_text(event_el, ["url", "link"]) or SETTINGS.umbc_events_url
            events.append(
                EventRecord(
                    event_id=str(raw_id),
                    title=title.strip(),
                    description=description.strip(),
                    start_time=start.strip(),
                    end_time=end.strip(),
                    location=location.strip(),
                    url=url.strip(),
                )
            )
        logger.info("Loaded %s events from XML API", len(events))
        return events

    def _fetch_from_html(self) -> list[EventRecord]:
        try:
            response = requests.get(
                SETTINGS.umbc_events_url,
                headers=self.headers,
                timeout=SETTINGS.request_timeout_seconds,
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning("UMBC events HTML page unavailable: %s", exc)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        candidates = soup.select("article, .event, .event-card, .featured-event, .post")
        events: list[EventRecord] = []

        for idx, node in enumerate(candidates[:250]):
            title_node = node.select_one("h1, h2, h3, .title")
            if not title_node:
                continue
            title = title_node.get_text(" ", strip=True)
            if len(title) < 5:
                continue

            description_node = node.select_one("p, .description, .summary")
            description = description_node.get_text(" ", strip=True) if description_node else ""
            date_node = node.select_one("time, .date, .event-date")
            when = date_node.get_text(" ", strip=True) if date_node else ""
            location_node = node.select_one(".location, .event-location")
            location = location_node.get_text(" ", strip=True) if location_node else "UMBC"
            link_node = node.select_one("a[href]")
            url = _normalize_link(link_node["href"]) if link_node else SETTINGS.umbc_events_url

            events.append(
                EventRecord(
                    event_id=f"html-{idx}-{_stable_id(title)}",
                    title=title,
                    description=description,
                    start_time=when,
                    end_time="",
                    location=location,
                    url=url,
                )
            )

        logger.info("Loaded %s events from HTML scrape", len(events))
        return events


def _first_text(element: ET.Element, tags: list[str]) -> str:
    for tag in tags:
        value = element.findtext(tag)
        if value:
            return value
    return ""


def _stable_id(text: str) -> str:
    cleaned = "".join(ch for ch in text.lower() if ch.isalnum())
    return cleaned[:24] or datetime.utcnow().strftime("%Y%m%d%H%M%S")


def _normalize_link(href: str) -> str:
    href = href.strip()
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return f"https://my.umbc.edu{href}"
    return f"https://my.umbc.edu/{href}"
