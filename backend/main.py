import io
import csv
import time
import json
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

load_dotenv()

import auth
import storage
import evaluator
import llm_client

app = FastAPI(title="HealthAI Lite")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

storage.init_db()

# ---- Serve frontend at http://localhost:8000 ----
_FRONTEND = Path(__file__).parent.parent / "frontend"
if _FRONTEND.exists():
    app.mount("/ui", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/ui/index.html")

# ---- Prometheus metrics (scraped by /api/metrics -> Prometheus -> Grafana) ----
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["path", "method"])
QUERY_LATENCY = Histogram("query_latency_seconds", "LLM query latency in seconds")
QUALITY_SCORE = Gauge("last_query_quality_score", "Quality score of the most recent query")
INGESTED_DATASETS = Gauge("ingested_datasets_total", "Number of datasets ingested")


@app.middleware("http")
async def track_requests(request, call_next):
    REQUEST_COUNT.labels(path=request.url.path, method=request.method).inc()
    return await call_next(request)


# ---------------------------------------------------------------- Auth -----
class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
def login(body: LoginRequest):
    if not auth.check_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"token": auth.create_token(body.username), "username": body.username}


@app.get("/api/auth/me")
def me(user: str = Depends(auth.require_auth)):
    return {"username": user}


# ------------------------------------------------------------ Ingestion ----
@app.post("/api/ingest/upload")
async def upload(file: UploadFile = File(...), user: str = Depends(auth.require_auth)):
    raw = await file.read()
    name = file.filename or "upload"
    ext = Path(name).suffix.lower()

    if ext == ".csv":
        text = raw.decode("utf-8", errors="ignore")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        columns = rows[0] if rows else []
        data_rows = rows[1:]
        sample = data_rows[:5]
        dataset_id = storage.save_dataset(name, "csv", len(data_rows), columns, sample)

    elif ext == ".pdf":
        text, page_count = "", 0
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            page_count = len(reader.pages)
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception:
            pass
        dataset_id = storage.save_dataset(name, "pdf", page_count, [], [], text)

    else:  # treat as plain text
        text = raw.decode("utf-8", errors="ignore")
        line_count = text.count("\n") + 1
        dataset_id = storage.save_dataset(name, "text", line_count, [], [], text)

    INGESTED_DATASETS.set(len(storage.list_datasets()))
    return storage.get_dataset(dataset_id)


@app.get("/api/ingest/datasets")
def datasets(user: str = Depends(auth.require_auth)):
    return storage.list_datasets()


# ----------------------------------------------------------------- Query ---
class QueryRequest(BaseModel):
    question: str
    dataset_id: int | None = None


@app.post("/api/query")
def query(body: QueryRequest, user: str = Depends(auth.require_auth)):
    context = None
    if body.dataset_id:
        ds = storage.get_dataset(body.dataset_id)
        if ds:
            if ds["text_preview"]:
                context = ds["text_preview"]
            else:
                sample = json.loads(ds["sample_json"])
                cols = json.loads(ds["columns_json"])
                context = f"Columns: {cols}\nSample rows: {sample}"

    with QUERY_LATENCY.time():
        answer, mocked, latency_ms = llm_client.get_answer(body.question, context)

    metrics = evaluator.evaluate(body.question, answer, context)
    tokens_est = max(1, int(len(answer.split()) * 1.3))

    storage.save_query(body.question, answer, body.dataset_id, mocked, metrics, latency_ms, tokens_est)
    QUALITY_SCORE.set(metrics["quality_score"])

    return {
        "question": body.question,
        "answer": answer,
        "mocked": mocked,
        "latency_ms": latency_ms,
        "tokens_est": tokens_est,
        "matrix": metrics,
    }


@app.get("/api/query/history")
def history(user: str = Depends(auth.require_auth)):
    return storage.list_queries()


# ------------------------------------------------------------- Dashboard ---
@app.get("/api/dashboard/stats")
def stats(user: str = Depends(auth.require_auth)):
    return storage.dashboard_stats()


# -------------------------------------------------------- Observability ----
@app.get("/api/metrics")
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/health")
def health():
    return {"status": "ok", "time": time.time()}


