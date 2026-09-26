"""Tiny SQLite store for run history."""
import json
import sqlite3
import threading
from datetime import datetime, timezone

from . import config

_lock = threading.Lock()
_conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.execute(
    """
    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trigger TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        result_json TEXT,
        raw_text TEXT,
        error TEXT,
        usage_json TEXT
    )
    """
)
_conn.commit()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_run(trigger: str) -> int:
    with _lock:
        cur = _conn.execute(
            "INSERT INTO runs (trigger, status, started_at) VALUES (?, 'running', ?)",
            (trigger, now_iso()),
        )
        _conn.commit()
        return cur.lastrowid


def finish_run(run_id: int, status: str, result=None, raw_text=None, error=None, usage=None):
    with _lock:
        _conn.execute(
            "UPDATE runs SET status=?, finished_at=?, result_json=?, raw_text=?, error=?, usage_json=? WHERE id=?",
            (
                status,
                now_iso(),
                json.dumps(result) if result is not None else None,
                raw_text,
                error,
                json.dumps(usage) if usage is not None else None,
                run_id,
            ),
        )
        _conn.commit()


def mark_stale_runs_failed():
    """If the server restarted mid-run, do not leave a run stuck as 'running'."""
    with _lock:
        _conn.execute(
            "UPDATE runs SET status='error', finished_at=?, error='Interrupted by a server restart' WHERE status='running'",
            (now_iso(),),
        )
        _conn.commit()


def _row(r, full: bool):
    if r is None:
        return None
    d = {
        "id": r["id"],
        "trigger": r["trigger"],
        "status": r["status"],
        "started_at": r["started_at"],
        "finished_at": r["finished_at"],
        "error": r["error"],
        "usage": json.loads(r["usage_json"]) if r["usage_json"] else None,
    }
    result = json.loads(r["result_json"]) if r["result_json"] else None
    if full:
        d["result"] = result
        d["raw_text"] = r["raw_text"]
    else:
        d["count"] = len(result.get("stocks", [])) if result else 0
    return d


def get_run(run_id: int):
    with _lock:
        r = _conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    return _row(r, True)


def latest_done():
    with _lock:
        r = _conn.execute(
            "SELECT * FROM runs WHERE status='done' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return _row(r, True)


def list_runs(limit: int = 30):
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row(r, False) for r in rows]


def count_manual_today() -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _lock:
        r = _conn.execute(
            "SELECT COUNT(*) AS c FROM runs WHERE trigger='manual' AND started_at >= ?",
            (today,),
        ).fetchone()
    return int(r["c"])
