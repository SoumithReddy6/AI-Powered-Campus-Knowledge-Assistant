from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from campus_assistant.config import EVAL_DATA_DIR, PROCESSED_DATA_DIR, SETTINGS, ensure_directories
from campus_assistant.data_models import Document
from campus_assistant.evaluation.benchmark import BenchmarkRunner
from campus_assistant.ingestion.pipeline import IngestionPipeline
from campus_assistant.retrieval.rag_pipeline import RAGPipeline
from campus_assistant.retrieval.vector_index import VectorIndex
from campus_assistant.utils.io import read_jsonl

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
INDEX_PATH = PROCESSED_DATA_DIR / "vector_index.pkl"

app = FastAPI(title="UMBC Campus Knowledge Assistant", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@dataclass
class RuntimeState:
    rag: RAGPipeline | None = None
    index_backend: str | None = None


STATE = RuntimeState()


class IngestRequest(BaseModel):
    synthetic_size: int = Field(default=120, ge=20, le=1000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class EvaluateRequest(BaseModel):
    qa_path: str = str(EVAL_DATA_DIR / "qa_gold.json")


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


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
def status() -> dict[str, object]:
    ensure_directories()
    docs = read_jsonl(PROCESSED_DATA_DIR / "documents.jsonl")
    return {
        "documents": len(docs),
        "index_exists": INDEX_PATH.exists(),
        "index_loaded": STATE.rag is not None,
        "index_backend": STATE.index_backend,
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
                "name": "Class Search Public",
                "type": "REAL_OR_SYNTHETIC",
                "url": "https://umbc.edu/go/class-search-public",
            },
        ],
    }


@app.post("/api/pipeline/ingest")
def ingest(payload: IngestRequest) -> dict[str, object]:
    ensure_directories()
    summary = IngestionPipeline().run(synthetic_size=payload.synthetic_size)
    return {
        "ok": True,
        "summary": summary,
    }


@app.post("/api/pipeline/build-index")
def build_index() -> dict[str, object]:
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


@app.post("/api/chat")
def chat(payload: ChatRequest) -> dict[str, object]:
    rag = _load_rag()
    if rag is None:
        raise HTTPException(status_code=409, detail="Index not ready. Run ingest and build-index first.")

    result = rag.answer(payload.message, top_k=payload.top_k)
    return {
        "ok": True,
        "result": result.to_dict(),
    }


@app.post("/api/evaluate")
def evaluate(payload: EvaluateRequest) -> dict[str, object]:
    rag = _load_rag()
    if rag is None:
        raise HTTPException(status_code=409, detail="Index not ready. Build index first.")

    qa_path = Path(payload.qa_path)
    if not qa_path.exists():
        raise HTTPException(status_code=400, detail=f"QA dataset not found: {qa_path}")

    output_path = PROCESSED_DATA_DIR / "evaluation_report.json"
    report = BenchmarkRunner(rag).run(qa_path=qa_path, output_path=output_path)
    return {
        "ok": True,
        "report": report,
        "output_path": str(output_path),
    }


def _load_rag() -> RAGPipeline | None:
    if STATE.rag is not None:
        return STATE.rag

    if not INDEX_PATH.exists():
        return None

    index = VectorIndex.load(INDEX_PATH)
    STATE.rag = RAGPipeline(index)
    STATE.index_backend = index.backend_name
    return STATE.rag
