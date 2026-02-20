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
DB_DIR = DATA_DIR / "db"


def _load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv_file(PROJECT_ROOT / ".env")


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
    openai_assistant_id: str | None = os.getenv("OPENAI_ASSISTANT_ID")
    openai_assistant_system_prompt: str | None = os.getenv("OPENAI_ASSISTANT_SYSTEM_PROMPT")
    openai_assistant_timeout_seconds: int = int(os.getenv("OPENAI_ASSISTANT_TIMEOUT_SECONDS", "40"))

    top_k: int = int(os.getenv("TOP_K", "5"))
    admin_api_token: str = os.getenv("ADMIN_API_TOKEN", "umbc-admin")


SETTINGS = Settings()


def ensure_directories() -> None:
    for path in [RAW_DATA_DIR, PROCESSED_DATA_DIR, SYNTHETIC_DATA_DIR, EVAL_DATA_DIR, DB_DIR]:
        path.mkdir(parents=True, exist_ok=True)
