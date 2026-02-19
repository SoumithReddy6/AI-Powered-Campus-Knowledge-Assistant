from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
SYNTHETIC_DATA_DIR = DATA_DIR / "synthetic"
EVAL_DATA_DIR = DATA_DIR / "eval"


@dataclass(frozen=True)
class Settings:
    umbc_events_url: str = "https://my.umbc.edu/events"
    umbc_events_api_url: str = "https://my.umbc.edu/api/v0/events.xml"
    umbc_academic_calendar_url: str = "https://registrar.umbc.edu/calendars/academic-calendars/"
    umbc_class_search_url: str = "https://umbc.edu/go/class-search-public"

    request_timeout_seconds: int = 25
    user_agent: str = (
        "CampusKnowledgeAssistant/0.1 "
        "(research project; contact: maintainer@example.com)"
    )

    embedding_backend: str = os.getenv("EMBEDDING_BACKEND", "auto")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    top_k: int = int(os.getenv("TOP_K", "5"))


SETTINGS = Settings()


def ensure_directories() -> None:
    for path in [RAW_DATA_DIR, PROCESSED_DATA_DIR, SYNTHETIC_DATA_DIR, EVAL_DATA_DIR]:
        path.mkdir(parents=True, exist_ok=True)
