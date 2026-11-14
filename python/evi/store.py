"""SQLite storage: HTTP cache + application state (watchlist, snapshots, manual inputs, alerts)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS http_cache (key TEXT PRIMARY KEY, fetched REAL, status INTEGER, body BLOB);
CREATE TABLE IF NOT EXISTS watchlist (ticker TEXT PRIMARY KEY, added TEXT, base_json TEXT);
CREATE TABLE IF NOT EXISTS score_snapshots (ts TEXT, ticker TEXT, health REAL, valuation REAL, earnings REAL, risk REAL,
    cls_idx INTEGER, price REAL, fv_base REAL, payload TEXT, PRIMARY KEY (ts, ticker));
CREATE TABLE IF NOT EXISTS estimate_snapshots (day TEXT, ticker TEXT, period TEXT, eps_est REAL, rev_est REAL, source TEXT,
    PRIMARY KEY (day, ticker, period));
CREATE TABLE IF NOT EXISTS manual_inputs (ticker TEXT, key TEXT, value TEXT, updated TEXT, PRIMARY KEY (ticker, key));
CREATE TABLE IF NOT EXISTS alerts (ts TEXT, ticker TEXT, kind TEXT, message TEXT, sent INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS scan_runs (ts TEXT PRIMARY KEY, params TEXT, n_companies INTEGER, duration_s REAL, errors TEXT);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ---------- HTTP cache ----------
    def cache_get(self, key: str, ttl_s: float) -> tuple[int, bytes] | None:
        with self._lock:
            row = self._conn.execute("SELECT fetched, status, body FROM http_cache WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        fetched, status, body = row
        if ttl_s >= 0 and time.time() - fetched > ttl_s:
            return None
        return status, body

    def cache_fetched_at(self, key: str) -> float | None:
        with self._lock:
            row = self._conn.execute("SELECT fetched FROM http_cache WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def cache_put(self, key: str, status: int, body: bytes) -> None:
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO http_cache VALUES (?,?,?,?)", (key, time.time(), status, body))
            self._conn.commit()

    def cache_clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM http_cache")
            self._conn.commit()

    # ---------- generic ----------
    def execute(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # ---------- watchlist ----------
    def watch_list(self) -> dict[str, dict]:
        return {t: {"added": a, "base": json.loads(b or "{}")} for t, a, b in self.query("SELECT ticker, added, base_json FROM watchlist")}

    def watch_add(self, ticker: str, added: str, base: dict) -> None:
        self.execute("INSERT OR REPLACE INTO watchlist VALUES (?,?,?)", (ticker, added, json.dumps(base)))

    def watch_remove(self, ticker: str) -> None:
        self.execute("DELETE FROM watchlist WHERE ticker=?", (ticker,))

    # ---------- manual inputs ----------
    def manual_get(self, ticker: str) -> dict[str, Any]:
        return {k: json.loads(v) for k, v in self.query("SELECT key, value FROM manual_inputs WHERE ticker=?", (ticker,))}

    def manual_set(self, ticker: str, key: str, value: Any, updated: str) -> None:
        if value in (None, ""):
            self.execute("DELETE FROM manual_inputs WHERE ticker=? AND key=?", (ticker, key))
        else:
            self.execute("INSERT OR REPLACE INTO manual_inputs VALUES (?,?,?,?)", (ticker, key, json.dumps(value), updated))

    # ---------- estimate snapshots (to measure revisions over time) ----------
    def estimate_save(self, day: str, ticker: str, period: str, eps: float | None, rev: float | None, source: str) -> None:
        self.execute("INSERT OR REPLACE INTO estimate_snapshots VALUES (?,?,?,?,?,?)", (day, ticker, period, eps, rev, source))

    def estimate_history(self, ticker: str) -> list[dict]:
        rows = self.query("SELECT day, period, eps_est, rev_est, source FROM estimate_snapshots WHERE ticker=? ORDER BY day", (ticker,))
        return [dict(day=d, period=p, eps_est=e, rev_est=r, source=s) for d, p, e, r, s in rows]

    # ---------- score snapshots / alerts ----------
    def snapshot_save(self, ts: str, ticker: str, row: dict[str, Any]) -> None:
        self.execute("INSERT OR REPLACE INTO score_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (ts, ticker, row.get("health"), row.get("valuation"), row.get("earnings"), row.get("risk"),
                      row.get("cls_idx"), row.get("price"), row.get("fv_base"), json.dumps(row.get("payload", {}))))

    def snapshot_last_two(self, ticker: str) -> list[dict]:
        rows = self.query("SELECT ts, health, valuation, earnings, risk, cls_idx, price, fv_base FROM score_snapshots WHERE ticker=? ORDER BY ts DESC LIMIT 2", (ticker,))
        keys = ["ts", "health", "valuation", "earnings", "risk", "cls_idx", "price", "fv_base"]
        return [dict(zip(keys, r)) for r in rows]

    def alert_add(self, ts: str, ticker: str, kind: str, message: str) -> None:
        self.execute("INSERT INTO alerts (ts, ticker, kind, message) VALUES (?,?,?,?)", (ts, ticker, kind, message))

    def alerts_recent(self, limit: int = 200) -> list[dict]:
        rows = self.query("SELECT ts, ticker, kind, message, sent FROM alerts ORDER BY ts DESC LIMIT ?", (limit,))
        return [dict(ts=a, ticker=b, kind=c, message=d, sent=e) for a, b, c, d, e in rows]

    def scan_log(self, ts: str, params: dict, n: int, dur: float, errors: list[str]) -> None:
        self.execute("INSERT OR REPLACE INTO scan_runs VALUES (?,?,?,?,?)", (ts, json.dumps(params), n, dur, json.dumps(errors[:200])))

    def last_scan(self) -> dict | None:
        r = self.query("SELECT ts, params, n_companies, duration_s, errors FROM scan_runs ORDER BY ts DESC LIMIT 1")
        if not r:
            return None
        ts, p, n, d, e = r[0]
        return dict(ts=ts, params=json.loads(p), n=n, duration=d, errors=json.loads(e))


_STORE: Store | None = None


def get_store(path: Path | None = None) -> Store:
    global _STORE
    if _STORE is None:
        from .config import load_settings
        _STORE = Store(path or load_settings().db_path)
    return _STORE
