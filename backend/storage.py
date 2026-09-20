"""
Single-file SQLite storage. No Postgres, no Kafka, no Qdrant — one file
(`data.db`) that ships with the demo and just works on any laptop.
"""
import sqlite3
import json
import time
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "data.db"


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS datasets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                kind TEXT NOT NULL,
                row_count INTEGER DEFAULT 0,
                columns_json TEXT DEFAULT '[]',
                sample_json TEXT DEFAULT '[]',
                text_preview TEXT DEFAULT '',
                uploaded_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                dataset_id INTEGER,
                mocked INTEGER DEFAULT 0,
                relevance REAL,
                groundedness REAL,
                coherence REAL,
                safety REAL,
                latency_ms REAL,
                tokens_est INTEGER,
                quality_score REAL,
                created_at REAL NOT NULL
            )
        """)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_dataset(filename, kind, row_count, columns, sample, text_preview=""):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO datasets (filename, kind, row_count, columns_json, sample_json, text_preview, uploaded_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (filename, kind, row_count, json.dumps(columns), json.dumps(sample), text_preview[:2000], time.time()),
        )
        return cur.lastrowid


def list_datasets():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM datasets ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def get_dataset(dataset_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
        return dict(row) if row else None


def save_query(question, answer, dataset_id, mocked, metrics, latency_ms, tokens_est):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO queries
               (question, answer, dataset_id, mocked, relevance, groundedness, coherence,
                safety, latency_ms, tokens_est, quality_score, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (question, answer, dataset_id, int(mocked), metrics["relevance"], metrics["groundedness"],
             metrics["coherence"], metrics["safety"], latency_ms, tokens_est, metrics["quality_score"],
             time.time()),
        )
        return cur.lastrowid


def list_queries(limit=20):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM queries ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def dashboard_stats():
    with get_conn() as conn:
        datasets_count = conn.execute("SELECT COUNT(*) c FROM datasets").fetchone()["c"]
        total_rows = conn.execute("SELECT COALESCE(SUM(row_count),0) s FROM datasets").fetchone()["s"]
        queries_count = conn.execute("SELECT COUNT(*) c FROM queries").fetchone()["c"]
        avg_quality = conn.execute("SELECT AVG(quality_score) a FROM queries").fetchone()["a"] or 0
        avg_latency = conn.execute("SELECT AVG(latency_ms) a FROM queries").fetchone()["a"] or 0
        trend = conn.execute(
            "SELECT id, quality_score, latency_ms, created_at FROM queries ORDER BY id DESC LIMIT 15"
        ).fetchall()
        recent = conn.execute(
            "SELECT id, question, quality_score, mocked, created_at FROM queries ORDER BY id DESC LIMIT 8"
        ).fetchall()
        return {
            "datasets_count": datasets_count,
            "total_rows": total_rows,
            "queries_count": queries_count,
            "avg_quality": round(avg_quality, 1),
            "avg_latency_ms": round(avg_latency, 1),
            "trend": [dict(r) for r in reversed(trend)],
            "recent_queries": [dict(r) for r in recent],
        }
