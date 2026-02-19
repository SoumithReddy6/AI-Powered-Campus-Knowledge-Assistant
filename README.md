# AI-Powered Campus Knowledge Assistant Using Institutional Data (UMBC)

A master’s-level end-to-end AI system that answers natural-language campus questions by combining:

- Real institutional data ingestion (UMBC events + registrar academic calendars)
- Synthetic fallback generation (class schedule only when public class search is inaccessible)
- Intent classification + NER-style entity extraction
- Query normalization for typo-tolerant and uneven-English prompts
- Retrieval-Augmented Generation (RAG) with semantic retrieval
- Evaluation with accuracy/precision/recall/F1, retrieval quality, correctness proxy, and latency
- A full web app (FastAPI + custom frontend) for ingestion, indexing, evaluation, and chat

## 1) Data Policy (Real First, Synthetic Fallback)

This project follows your requirement strictly:

- Use real data whenever publicly available.
- Use synthetic data only where public access is blocked.

### Active sources

1. Real: `https://my.umbc.edu/events`
   - Ingestion module: `src/campus_assistant/ingestion/events_ingestor.py`
   - Strategy: XML API first (`/api/v0/events.xml`) then HTML fallback.

2. Real: `https://registrar.umbc.edu/calendars/academic-calendars/`
   - Ingestion module: `src/campus_assistant/ingestion/calendar_ingestor.py`
   - Strategy: crawl term/deadline links and extract date-deadline lines.

3. Conditional Real / Synthetic fallback: `https://umbc.edu/go/class-search-public`
   - Ingestion module: `src/campus_assistant/ingestion/class_schedule_ingestor.py`
   - Strategy:
     - If public schedule table is accessible: parse real classes.
     - If auth/login/SSO/no table: generate synthetic graduate-level class schedules with deterministic seed.

## 2) System Architecture

1. Ingestion
   - Collect, parse, normalize multi-source campus data.

2. NLP layer
   - `IntentClassifier`: rule-based interpretable baseline for campus intents.
   - `CampusEntityExtractor`: extracts building/service/course/room entities.
   - `QueryNormalizer`: auto-corrects misspellings and normalizes uneven prompts before retrieval.

3. Retrieval layer
   - `VectorIndex`:
     - Dense embeddings (`sentence-transformers`) when available.
     - Automatic fallback to TF-IDF semantic retrieval.

4. RAG answering
   - Query intent + entities + retrieval context.
   - Optional OpenAI generation if `OPENAI_API_KEY` exists.
   - Otherwise deterministic evidence-grounded template answers.

5. Evaluation
   - Intent: accuracy, precision, recall, F1.
   - Retrieval: hit-rate@5, MRR.
   - Response quality: token-overlap correctness proxy.
   - Performance: avg and p95 latency.

6. Web application
   - FastAPI backend APIs for ingestion, indexing, chat, and evaluation.
   - Custom HTML/CSS/JS frontend (responsive UI, evidence panel, metrics cards).

## 3) Repository Layout

```
.
├── data/
│   ├── eval/qa_gold.json
│   ├── raw/
│   ├── processed/
│   └── synthetic/
├── scripts/
│   ├── ingest_all.py
│   ├── build_index.py
│   ├── run_assistant.py
│   ├── evaluate.py
│   └── run_web_app.sh
├── src/campus_assistant/
│   ├── app/cli.py
│   ├── ingestion/
│   ├── nlp/
│   ├── retrieval/
│   ├── evaluation/
│   ├── web/
│   └── utils/
├── tests/
├── pyproject.toml
└── requirements.txt
```

## 4) Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Optional features:

```bash
pip install -e ".[llm,dense,dev]"
```

## 5) Run as Website (Primary)

Start the web app:

```bash
./scripts/run_web_app.sh
```

or run directly:

```bash
uvicorn campus_assistant.web.server:app --reload --host 0.0.0.0 --port 8000
```

Then open:

```bash
http://localhost:8000
```

Features in the website:

- Ingest UMBC real data with one click
- Automatic synthetic fallback only for class schedule when needed
- Build vector index from the UI
- Ask natural-language questions in chat (with auto-correction of spelling and uneven English)
- Inspect retrieved evidence and metadata
- Run evaluation and view accuracy/retrieval/latency metrics

## 6) CLI Pipeline (Secondary)

### A) Ingest data (real first, synthetic fallback for classes)

```bash
python -m campus_assistant.app.cli ingest
```

### B) Build retrieval index

```bash
python -m campus_assistant.app.cli build-index
```

### C) Start interactive assistant

```bash
python -m campus_assistant.app.cli chat
```

### D) Evaluate

```bash
python -m campus_assistant.app.cli evaluate
```

Evaluation report is saved at:

- `data/processed/evaluation_report.json`

## 7) Optional OpenAI Integration

Set:

```bash
export OPENAI_API_KEY="your_key"
export OPENAI_MODEL="gpt-4o-mini"
```

Without this, the project still works with local fallback generation.

## 8) Master’s-Level Extensions You Can Add

1. Supervised intent model fine-tuning on annotated campus queries.
2. Hybrid retriever (BM25 + dense) with re-ranking.
3. Temporal reasoning for deadline/event questions.
4. Confidence calibration and abstention policy.
5. User simulation and online evaluation loops.
6. Data drift monitoring for calendar and event changes.

## 9) Testing

```bash
pytest -q
```

Included tests validate:

- Class schedule synthetic fallback behavior
- Core intent classification
- Entity extraction baseline

## 10) Git Push

If this folder is not initialized yet:

```bash
git init
git add .
git commit -m "Initial master-level UMBC campus knowledge assistant"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

If your remote already exists locally, skip `git remote add origin`.
