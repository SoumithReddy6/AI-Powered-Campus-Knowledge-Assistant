from __future__ import annotations

import json
import sqlite3
import secrets
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from campus_assistant.config import EVAL_DATA_DIR, PROCESSED_DATA_DIR, RAW_DATA_DIR, SETTINGS, ensure_directories
from campus_assistant.data_models import Document, QueryResult
from campus_assistant.db.multi_db import (
    build_class_catalog_answer,
    class_records_from_csv_text,
    fetch_calendar_records,
    fetch_event_records,
    fetch_event_promotions,
    fetch_class_records,
    get_db_counts,
    init_databases,
    upsert_calendar_rows,
    upsert_class_rows,
    upsert_event_rows,
)
from campus_assistant.evaluation.benchmark import BenchmarkRunner
from campus_assistant.ingestion.pipeline import IngestionPipeline
from campus_assistant.llm import answer_with_domain_assistant
from campus_assistant.nlp.intent import IntentClassifier
from campus_assistant.nlp.query_normalizer import QueryNormalizer
from campus_assistant.retrieval.rag_pipeline import RAGPipeline
from campus_assistant.retrieval.vector_index import VectorIndex
from campus_assistant.utils.io import read_jsonl

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
INDEX_PATH = PROCESSED_DATA_DIR / "vector_index.pkl"
STUDIO_SESSION_COOKIE = "studio_session"
STUDIO_SESSION_TTL_SECONDS = 60 * 60 * 10

app = FastAPI(title="UMBC Campus Knowledge Assistant", version="2.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@dataclass
class RuntimeState:
    rag: RAGPipeline | None = None
    index_backend: str | None = None
    intent_classifier: IntentClassifier = field(default_factory=IntentClassifier)
    query_normalizer: QueryNormalizer = field(default_factory=QueryNormalizer)
    studio_sessions: dict[str, float] = field(default_factory=dict)


STATE = RuntimeState()


class IngestRequest(BaseModel):
    synthetic_size: int = Field(default=120, ge=20, le=1000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class EvaluateRequest(BaseModel):
    qa_path: str = str(EVAL_DATA_DIR / "qa_gold.json")


class AdminCsvUploadRequest(BaseModel):
    admin_token: str
    csv_text: str


class AdminClassUpsertRequest(BaseModel):
    admin_token: str
    records: list[dict[str, Any]]


class AdminManualIngestRequest(BaseModel):
    admin_token: str
    source_type: Literal["events", "calendars", "classes"]
    payload_json: str


class StudioLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=500)


class StudioCsvUploadRequest(BaseModel):
    csv_text: str


class StudioClassUpsertRequest(BaseModel):
    records: list[dict[str, Any]]


class StudioManualIngestRequest(BaseModel):
    source_type: Literal["events", "calendars", "classes"]
    payload_json: str


@app.on_event("startup")
def startup() -> None:
    ensure_directories()
    init_databases()
    _bootstrap_query_normalizer_from_docs()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_name": "UMBC Campus Knowledge Assistant",
            "top_k": SETTINGS.top_k,
        },
    )


@app.get("/studio/login", response_class=HTMLResponse)
def studio_login_page(request: Request):
    if _is_studio_authorized(request):
        return RedirectResponse(url="/studio", status_code=303)
    return templates.TemplateResponse(
        "studio_login.html",
        {
            "request": request,
            "app_name": "UMBC Data Studio",
        },
    )


@app.get("/studio", response_class=HTMLResponse)
def studio_page(request: Request):
    if not _is_studio_authorized(request):
        return RedirectResponse(url="/studio/login", status_code=303)
    return templates.TemplateResponse(
        "studio.html",
        {
            "request": request,
            "app_name": "UMBC Data Studio",
            "top_k": SETTINGS.top_k,
        },
    )


@app.post("/api/studio/login")
def studio_login(payload: StudioLoginRequest, response: Response) -> dict[str, Any]:
    _authorize_admin(payload.password)
    session_id = _create_studio_session()
    response.set_cookie(
        key=STUDIO_SESSION_COOKIE,
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=STUDIO_SESSION_TTL_SECONDS,
    )
    return {"ok": True}


@app.post("/api/studio/logout")
def studio_logout(request: Request, response: Response) -> dict[str, Any]:
    _delete_studio_session(request.cookies.get(STUDIO_SESSION_COOKIE))
    response.delete_cookie(STUDIO_SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
def status() -> dict[str, Any]:
    ensure_directories()
    init_databases()
    docs = read_jsonl(PROCESSED_DATA_DIR / "documents.jsonl")
    db_counts = get_db_counts()

    return {
        "documents": len(docs),
        "index_exists": INDEX_PATH.exists(),
        "index_loaded": STATE.rag is not None,
        "index_backend": STATE.index_backend,
        "db_counts": db_counts,
        "data_sources": [
            {
                "name": "myUMBC Events",
                "type": "REAL",
                "url": "https://my.umbc.edu/events",
            },
            {
                "name": "Registrar Academic Calendars",
                "type": "REAL",
                "url": "https://registrar.umbc.edu/calendars/academic-calendars/",
            },
            {
                "name": "Class Database",
                "type": "ADMIN_MANAGED",
                "url": "Managed via protected Data Studio (/studio)",
            },
        ],
    }


@app.get("/api/promotions")
def promotions(limit: int = Query(default=6, ge=1, le=20)) -> dict[str, Any]:
    init_databases()
    rows = fetch_event_promotions(limit=limit)
    if rows:
        return {
            "ok": True,
            "source": "events_db",
            "count": len(rows),
            "items": [
                {
                    "id": row.get("event_id", ""),
                    "title": row.get("title", ""),
                    "summary": row.get("description", ""),
                    "when": row.get("start_time", ""),
                    "location": row.get("location", ""),
                    "url": row.get("url", ""),
                    "source": row.get("source", "umbc_events"),
                }
                for row in rows
            ],
        }

    fallback = _fallback_promotions()[:limit]
    return {
        "ok": True,
        "source": "fallback",
        "count": len(fallback),
        "items": fallback,
    }


@app.get("/api/studio/status")
def studio_status(request: Request) -> dict[str, Any]:
    _require_studio_access(request)
    return status()


@app.post("/api/studio/pipeline/ingest")
def studio_ingest(request: Request, payload: IngestRequest) -> dict[str, Any]:
    _require_studio_access(request)
    return _run_ingestion(payload.synthetic_size)


@app.post("/api/studio/pipeline/build-index")
def studio_build_index(request: Request) -> dict[str, Any]:
    _require_studio_access(request)
    return _run_build_index()


@app.post("/api/studio/evaluate")
def studio_evaluate(request: Request, payload: EvaluateRequest) -> dict[str, Any]:
    _require_studio_access(request)
    return _run_evaluation(payload.qa_path)


@app.post("/api/studio/classes/upload-csv")
def studio_upload_classes_csv(request: Request, payload: StudioCsvUploadRequest) -> dict[str, Any]:
    _require_studio_access(request)
    init_databases()

    try:
        rows = class_records_from_csv_text(payload.csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not rows:
        raise HTTPException(status_code=400, detail="No valid rows found in CSV.")

    upserted = upsert_class_rows(rows)
    return {
        "ok": True,
        "upserted": upserted,
        "db_counts": get_db_counts(),
    }


@app.post("/api/studio/classes/upsert")
def studio_upsert_classes(request: Request, payload: StudioClassUpsertRequest) -> dict[str, Any]:
    _require_studio_access(request)
    init_databases()
    if not payload.records:
        raise HTTPException(status_code=400, detail="records must not be empty")
    upserted = upsert_class_rows(payload.records)
    return {
        "ok": True,
        "upserted": upserted,
        "db_counts": get_db_counts(),
    }


@app.post("/api/studio/ingestion/manual")
def studio_manual_ingestion(request: Request, payload: StudioManualIngestRequest) -> dict[str, Any]:
    _require_studio_access(request)
    init_databases()
    rows = _rows_from_manual_payload(payload.payload_json)
    if not rows:
        raise HTTPException(status_code=400, detail="payload_json does not contain any rows")
    upserted = _upsert_by_source_type(payload.source_type, rows)
    return {
        "ok": True,
        "source_type": payload.source_type,
        "upserted": upserted,
        "db_counts": get_db_counts(),
    }


@app.get("/api/studio/classes")
def studio_list_classes(
    request: Request,
    department: Optional[str] = None,
    term: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    _require_studio_access(request)
    rows = fetch_class_records(department=department, term=term, limit=limit)
    return {"ok": True, "count": len(rows), "rows": rows}


@app.post("/api/pipeline/ingest")
def ingest(request: Request, payload: IngestRequest) -> dict[str, Any]:
    _require_studio_access(request)
    return _run_ingestion(payload.synthetic_size)


@app.post("/api/pipeline/build-index")
def build_index(request: Request) -> dict[str, Any]:
    _require_studio_access(request)
    return _run_build_index()


@app.post("/api/chat")
def chat(payload: ChatRequest) -> dict[str, Any]:
    normalized = STATE.query_normalizer.normalize(payload.message)
    normalized_query = normalized.corrected or payload.message
    intent = STATE.intent_classifier.predict(normalized_query)

    start = time.perf_counter()

    if _should_route_to_class_database(normalized_query, intent.label):
        answer, sources, route_meta = build_class_catalog_answer(normalized_query)
        assistant_answer = answer_with_domain_assistant(
            query=normalized_query,
            context=_context_from_sources(
                query=normalized_query,
                route_label="class_database",
                sources=sources,
                fallback_answer=answer,
            ),
            route_label="class_database",
        )
        if assistant_answer:
            answer = assistant_answer

        result = QueryResult(
            query=payload.message,
            answer=answer,
            intent="class_schedule",
            entities=[],
            sources=sources,
            latency_ms=round((time.perf_counter() - start) * 1000, 2),
            normalized_query=normalized_query,
            correction_applied=normalized.applied,
            corrections=normalized.changes,
        )
        return {
            "ok": True,
            "route": "class_database",
            "route_metadata": route_meta,
            "result": result.to_dict(),
        }

    rag = _load_rag()
    if rag is None:
        fallback_context, fallback_sources = _provider_context_bundle(normalized_query, intent.label)
        assistant_status = _assistant_runtime_status()
        assistant_answer = answer_with_domain_assistant(
            query=normalized_query,
            context=fallback_context,
            route_label="provider_fallback",
        )

        fallback = QueryResult(
            query=payload.message,
            answer=assistant_answer
            or _assistant_unavailable_message(assistant_status),
            intent=intent.label,
            entities=[],
            sources=fallback_sources,
            latency_ms=round((time.perf_counter() - start) * 1000, 2),
            normalized_query=normalized_query,
            correction_applied=normalized.applied,
            corrections=normalized.changes,
        )
        return {
            "ok": True,
            "route": "fallback",
            "route_metadata": {"assistant_status": assistant_status},
            "result": fallback.to_dict(),
        }

    result = rag.answer(payload.message, top_k=payload.top_k)
    return {
        "ok": True,
        "route": "rag",
        "result": result.to_dict(),
    }


@app.post("/api/evaluate")
def evaluate(request: Request, payload: EvaluateRequest) -> dict[str, Any]:
    _require_studio_access(request)
    return _run_evaluation(payload.qa_path)


@app.post("/api/admin/classes/upload-csv")
def admin_upload_classes_csv(payload: AdminCsvUploadRequest) -> dict[str, Any]:
    _authorize_admin(payload.admin_token)
    init_databases()

    try:
        rows = class_records_from_csv_text(payload.csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not rows:
        raise HTTPException(status_code=400, detail="No valid rows found in CSV.")

    upserted = upsert_class_rows(rows)
    return {
        "ok": True,
        "upserted": upserted,
        "db_counts": get_db_counts(),
    }


@app.post("/api/admin/classes/upsert")
def admin_upsert_classes(payload: AdminClassUpsertRequest) -> dict[str, Any]:
    _authorize_admin(payload.admin_token)
    init_databases()

    if not payload.records:
        raise HTTPException(status_code=400, detail="records must not be empty")

    upserted = upsert_class_rows(payload.records)
    return {
        "ok": True,
        "upserted": upserted,
        "db_counts": get_db_counts(),
    }


@app.post("/api/admin/ingestion/manual")
def admin_manual_ingestion(payload: AdminManualIngestRequest) -> dict[str, Any]:
    _authorize_admin(payload.admin_token)
    init_databases()

    rows = _rows_from_manual_payload(payload.payload_json)
    if not rows:
        raise HTTPException(status_code=400, detail="payload_json does not contain any rows")

    upserted = _upsert_by_source_type(payload.source_type, rows)

    return {
        "ok": True,
        "source_type": payload.source_type,
        "upserted": upserted,
        "db_counts": get_db_counts(),
    }


@app.get("/api/admin/classes")
def admin_list_classes(
    admin_token: str,
    department: Optional[str] = None,
    term: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    _authorize_admin(admin_token)
    rows = fetch_class_records(department=department, term=term, limit=limit)
    return {
        "ok": True,
        "count": len(rows),
        "rows": rows,
    }


@app.get("/api/classes/catalog")
def class_catalog(
    department: Optional[str] = None,
    term: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    rows = fetch_class_records(department=department, term=term, limit=limit)
    return {
        "ok": True,
        "count": len(rows),
        "rows": rows,
    }


@app.get("/api/provider/status")
def provider_status() -> dict[str, Any]:
    ensure_directories()
    init_databases()
    return {
        "ok": True,
        "provider": "studio_databases",
        "db_counts": get_db_counts(),
        "endpoints": {
            "events": "/api/provider/events",
            "calendars": "/api/provider/calendars",
            "classes": "/api/provider/classes",
        },
    }


@app.get("/api/provider/events")
def provider_events(limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
    init_databases()
    rows = fetch_event_records(limit=limit)
    return {"ok": True, "count": len(rows), "rows": rows}


@app.get("/api/provider/calendars")
def provider_calendars(
    term: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    init_databases()
    rows = fetch_calendar_records(term=term, limit=limit)
    return {"ok": True, "count": len(rows), "rows": rows}


@app.get("/api/provider/classes")
def provider_classes(
    department: Optional[str] = None,
    term: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    init_databases()
    rows = fetch_class_records(department=department, term=term, limit=limit)
    return {"ok": True, "count": len(rows), "rows": rows}


def _provider_context_bundle(query: str, intent_label: str) -> tuple[str, list[dict[str, Any]]]:
    init_databases()
    sources: list[dict[str, Any]] = []
    lines: list[str] = []

    event_limit = 8 if intent_label in {"event", "facility_hours", "location"} else 5
    calendar_limit = 10 if intent_label in {"time", "facility_hours"} else 6

    events = fetch_event_records(limit=event_limit)
    calendars = fetch_calendar_records(limit=calendar_limit)
    classes = fetch_class_records(limit=6)

    for row in events:
        title = row.get("title", "Untitled event")
        description = textwrap.shorten(str(row.get("description", "")), width=170, placeholder="...")
        when = row.get("start_time", "")
        location = row.get("location", "")
        lines.append(f"[event] {title} | when={when} | location={location} | {description}")
        sources.append(
            {
                "doc_id": f"provider-event-{row.get('event_id', '')}",
                "title": title,
                "source_type": "event_database",
                "score": 1.0,
                "metadata": row,
            }
        )

    for row in calendars:
        detail = textwrap.shorten(str(row.get("detail", "")), width=170, placeholder="...")
        term = row.get("term", "")
        date_text = row.get("date_text", "")
        lines.append(f"[calendar] term={term} | date={date_text} | {detail}")
        sources.append(
            {
                "doc_id": f"provider-calendar-{row.get('entry_id', '')}",
                "title": f"{term} {date_text}".strip() or "Calendar entry",
                "source_type": "calendar_database",
                "score": 1.0,
                "metadata": row,
            }
        )

    for row in classes:
        code = row.get("course_code", "")
        title = row.get("course_title", "")
        term = row.get("term", "")
        instructor = row.get("instructor", "")
        lines.append(f"[class] term={term} | {code} {title} | instructor={instructor}")
        sources.append(
            {
                "doc_id": f"provider-class-{row.get('class_id', '')}-{row.get('section', '')}",
                "title": f"{code} - {title}".strip(" -"),
                "source_type": "class_database",
                "score": 1.0,
                "metadata": row,
            }
        )

    context = (
        f"Question: {query}\n"
        "Campus provider records:\n"
        + "\n".join(lines[:45])
    )
    return context, sources[:45]


def _context_from_sources(
    *,
    query: str,
    route_label: str,
    sources: list[dict[str, Any]],
    fallback_answer: str,
) -> str:
    lines: list[str] = [
        f"Question: {query}",
        f"Route: {route_label}",
        "Baseline answer from deterministic campus DB retrieval:",
        textwrap.shorten(fallback_answer, width=550, placeholder="..."),
    ]

    for source in sources[:20]:
        meta = source.get("metadata", {})
        lines.append(
            f"[{source.get('source_type', 'source')}] {source.get('title', '')} | "
            f"term={meta.get('term', '')} | section={meta.get('section', '')} | "
            f"instructor={meta.get('instructor', '')}"
        )
    return "\n".join(lines)


def _assistant_runtime_status() -> dict[str, Any]:
    has_key = bool(SETTINGS.openai_api_key)
    has_assistant_id = bool(SETTINGS.openai_assistant_id)
    try:
        import openai  # noqa: F401

        sdk_installed = True
    except Exception:
        sdk_installed = False

    return {
        "has_openai_api_key": has_key,
        "has_openai_assistant_id": has_assistant_id,
        "openai_sdk_installed": sdk_installed,
    }


def _assistant_unavailable_message(status: dict[str, Any]) -> str:
    missing: list[str] = []
    if not status.get("has_openai_api_key"):
        missing.append("OPENAI_API_KEY")
    if not status.get("has_openai_assistant_id"):
        missing.append("OPENAI_ASSISTANT_ID")
    if not status.get("openai_sdk_installed"):
        missing.append("openai SDK")

    if missing:
        return (
            "Pretrained assistant is offline: missing "
            + ", ".join(missing)
            + ". Configure them and retry. "
            "Data admin can ingest/build index via Data Studio."
        )

    return (
        "Pretrained assistant could not answer this request right now. "
        "Try again, or ingest/build index in Data Studio for retrieval fallback."
    )


def _run_ingestion(synthetic_size: int) -> dict[str, Any]:
    ensure_directories()
    init_databases()

    summary = IngestionPipeline().run(synthetic_size=synthetic_size)
    sync_summary = _sync_databases_from_raw_files()
    _bootstrap_query_normalizer_from_docs()

    return {
        "ok": True,
        "summary": summary,
        "db_sync": sync_summary,
        "db_counts": get_db_counts(),
    }


def _run_build_index() -> dict[str, Any]:
    ensure_directories()
    rows = read_jsonl(PROCESSED_DATA_DIR / "documents.jsonl")
    if not rows:
        raise HTTPException(status_code=400, detail="No processed documents found. Run ingestion first.")

    documents = [Document(**row) for row in rows]
    index = VectorIndex()
    index.build(documents)
    index.save(INDEX_PATH)

    STATE.rag = RAGPipeline(index)
    STATE.index_backend = index.backend_name

    return {
        "ok": True,
        "documents": len(documents),
        "index_backend": index.backend_name,
        "index_path": str(INDEX_PATH),
    }


def _run_evaluation(qa_path_raw: str) -> dict[str, Any]:
    rag = _load_rag()
    if rag is None:
        raise HTTPException(status_code=409, detail="Index not ready. Build index first.")

    qa_path = Path(qa_path_raw)
    if not qa_path.exists():
        raise HTTPException(status_code=400, detail=f"QA dataset not found: {qa_path}")

    output_path = PROCESSED_DATA_DIR / "evaluation_report.json"
    report = BenchmarkRunner(rag).run(qa_path=qa_path, output_path=output_path)
    return {
        "ok": True,
        "report": report,
        "output_path": str(output_path),
    }


def _upsert_by_source_type(source_type: str, rows: list[dict[str, Any]]) -> int:
    try:
        if source_type == "events":
            return upsert_event_rows(rows)
        if source_type == "calendars":
            return upsert_calendar_rows(rows)
        return upsert_class_rows(rows)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=400, detail=f"Database constraint error: {exc}")


def _create_studio_session() -> str:
    _cleanup_studio_sessions()
    session_id = secrets.token_urlsafe(32)
    expires_at = time.time() + STUDIO_SESSION_TTL_SECONDS
    STATE.studio_sessions[session_id] = expires_at
    return session_id


def _delete_studio_session(session_id: Optional[str]) -> None:
    if not session_id:
        return
    STATE.studio_sessions.pop(session_id, None)


def _cleanup_studio_sessions() -> None:
    now = time.time()
    expired = [sid for sid, exp in STATE.studio_sessions.items() if exp <= now]
    for sid in expired:
        STATE.studio_sessions.pop(sid, None)


def _is_studio_authorized(request: Request) -> bool:
    _cleanup_studio_sessions()
    session_id = request.cookies.get(STUDIO_SESSION_COOKIE)
    if not session_id:
        return False
    return session_id in STATE.studio_sessions


def _require_studio_access(request: Request) -> None:
    if not _is_studio_authorized(request):
        raise HTTPException(status_code=401, detail="Studio authorization required.")


def _load_rag() -> RAGPipeline | None:
    if STATE.rag is not None:
        return STATE.rag

    if not INDEX_PATH.exists():
        return None

    index = VectorIndex.load(INDEX_PATH)
    STATE.rag = RAGPipeline(index)
    STATE.index_backend = index.backend_name
    return STATE.rag


def _sync_databases_from_raw_files() -> dict[str, int]:
    events = read_jsonl(RAW_DATA_DIR / "events.jsonl")
    calendars = read_jsonl(RAW_DATA_DIR / "academic_calendars.jsonl")
    classes = read_jsonl(RAW_DATA_DIR / "class_schedules.jsonl")

    return {
        "events_upserted": upsert_event_rows(events),
        "calendar_upserted": upsert_calendar_rows(calendars),
        "class_upserted": upsert_class_rows(classes),
    }


def _should_route_to_class_database(query: str, intent_label: str) -> bool:
    if intent_label == "class_schedule":
        return True

    lowered = query.lower()
    has_class_terms = any(token in lowered for token in ["class", "classes", "course", "courses", "section", "semester", "term"])
    has_department_hint = any(
        token in lowered
        for token in [
            "data",
            "data stream",
            "computer science",
            "cmsc",
            "information systems",
            "is ",
            "math",
            "statistics",
        ]
    )
    return has_class_terms and has_department_hint


def _authorize_admin(admin_token: str) -> None:
    if admin_token != SETTINGS.admin_api_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")


def _bootstrap_query_normalizer_from_docs() -> None:
    rows = read_jsonl(PROCESSED_DATA_DIR / "documents.jsonl")
    if not rows:
        return

    docs = [Document(**row) for row in rows]
    STATE.query_normalizer.bootstrap_from_documents(docs)


def _fallback_promotions() -> list[dict[str, str]]:
    return [
        {
            "id": "fallback-events",
            "title": "Explore Featured UMBC Events",
            "summary": "Career fairs, research talks, and student life events are listed on myUMBC.",
            "when": "Updated daily",
            "location": "myUMBC",
            "url": "https://my.umbc.edu/events",
            "source": "fallback",
        },
        {
            "id": "fallback-calendar",
            "title": "Track Academic Deadlines",
            "summary": "Use registrar calendars for add/drop, graduation, and enrollment milestones.",
            "when": "Current and future terms",
            "location": "Registrar Office",
            "url": "https://registrar.umbc.edu/calendars/academic-calendars/",
            "source": "fallback",
        },
    ]


def _rows_from_manual_payload(payload_json: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc.msg}")

    if isinstance(parsed, list):
        rows = parsed
    elif isinstance(parsed, dict) and isinstance(parsed.get("records"), list):
        rows = parsed["records"]
    else:
        raise HTTPException(
            status_code=400,
            detail="payload_json must be a JSON array of objects or {'records': [...]}",
        )

    valid_rows: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            valid_rows.append(row)
    return valid_rows
