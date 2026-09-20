# HealthAI Lite

A stripped-down, single-service rebuild of the original microservices
platform. Same four pillars — **login, dashboard, AI query with an
evaluation matrix, and data ingestion** — but one FastAPI backend, one
SQLite file, and a plain HTML/JS frontend. No Kafka, no Postgres, no
Qdrant, no Kubernetes. Runs on a laptop with no internet in under a minute.

## What's actually real here

- **Login** — real signed session tokens (HMAC), not fake. Credentials in `backend/.env`.
- **Ingestion** — really parses CSV/PDF/TXT and stores them in SQLite; you can query against them.
- **AI Query** — calls a real LLM if you put an API key in `.env` (works with OpenAI or any
  OpenAI-compatible endpoint: Groq, Together, OpenRouter, local Ollama). With no key it falls
  back to a template answer so the app never breaks mid-demo — a small "MOCK MODE" badge is
  shown honestly when that happens.
- **Evaluation matrix** — a real, explainable scoring function (relevance / groundedness /
  coherence / safety → composite quality score). No external eval service, just clear math in
  `backend/evaluator.py` — good if anyone asks you to explain how it works.
- **Metrics/Grafana/Prometheus** — the backend exposes real Prometheus metrics at
  `/api/metrics`; `docker-compose.yml` optionally spins up Prometheus + Grafana with a
  dashboard already provisioned (request counts, latency, live quality score).

## Fastest way to run it (no Docker)

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # edit if you have an LLM API key, otherwise leave as-is
uvicorn main:app --reload --port 8000
```

Then just open `frontend/index.html` directly in a browser (or run
`python -m http.server 5500` inside `frontend/` and visit
`http://localhost:5500`). Login with `admin` / `admin123`.

## Full showcase mode (with Grafana/Prometheus dashboards)

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

- App backend: http://localhost:8000
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3001 (anonymous access enabled, dashboard auto-loads)

Open `frontend/index.html` in a browser same as above — the frontend is
static, so it isn't part of the compose stack.

## Demo flow

1. Sign in on the login page.
2. Go to **Data Ingestion**, upload a small CSV (or any .txt/.pdf).
3. Go to **AI Query**, pick that dataset from the dropdown, ask a question
   related to it. The **evaluation matrix** renders first — that's the
   headline output — with the model's answer shown below it as secondary.
4. Go to **Dashboard** to see the quality/latency trend update live.
5. If you spun up the monitoring stack, open Grafana to show the same
   numbers as real time-series — this is the part that reads as
   "production observability" without needing the rest of the original
   microservices/Kafka/Kubernetes setup.

## Project structure

```
healthai-lite/
├── backend/
│   ├── main.py          # all API routes
│   ├── auth.py          # signed session tokens
│   ├── storage.py        # SQLite persistence
│   ├── evaluator.py      # evaluation matrix scoring
│   ├── llm_client.py     # real LLM call + offline fallback
│   └── requirements.txt
├── frontend/
│   ├── index.html        # login
│   ├── dashboard.html
│   ├── query.html         # AI query + evaluation matrix
│   ├── ingest.html
│   └── assets/
├── monitoring/            # optional Prometheus + Grafana provisioning
└── docker-compose.yml
```

## Honest notes for you (not for the demo)

- This intentionally does **not** do real vector search / RAG — the
  "context" for a query is just the raw sample/text of the dataset you
  pick, passed straight into the prompt. That's fine for a small demo
  file; it will not scale to a big document set.
- The evaluation metrics are simple, transparent heuristics (word overlap,
  sentence-length heuristics, keyword safety screen) — not a trained
  eval model. They're real and defensible, just not research-grade.
- If asked, be upfront that this is a simplified version built for a
  focused demo rather than the full original architecture.
