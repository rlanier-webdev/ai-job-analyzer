import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def init_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analysis (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT    NOT NULL,
            job_title   TEXT,
            job_company TEXT,
            score       INTEGER,
            should_apply INTEGER,
            result_json TEXT    NOT NULL
        )
    """)
    conn.commit()
    return conn


def save_analysis(conn: sqlite3.Connection, data: dict) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO analysis (created_at, job_title, job_company, score, should_apply, result_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            now,
            data.get("job_title"),
            data.get("job_company"),
            data.get("qualification_score"),
            1 if data.get("should_apply") else 0,
            json.dumps(data),
        ),
    )
    conn.commit()
    return cur.lastrowid


def list_analysis(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, created_at, job_title, job_company, score, should_apply FROM analysis ORDER BY id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_analysis(conn: sqlite3.Connection, analysis_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM analysis WHERE id = ?", (analysis_id,)
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data.update(json.loads(data.pop("result_json")))
    return data
