"""Persistent memory for agent theses and PM decisions.

Keyed by (ticker, timestamp). Records are stored as JSON blobs so we don't
couple this layer to whatever shape AgentThesis / PM decision objects take.

ponytail: SQLite (stdlib, zero deps) for local dev. One flat table, JSON
payloads. Migrate to Postgres by swapping the connection (same SQL is
Postgres-compatible except the autoincrement PK) or to a graph DB later.
"""

import json
import sqlite3
from datetime import datetime, timezone

THESIS = "thesis"
DECISION = "decision"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker  TEXT NOT NULL,
    ts      TEXT NOT NULL,          -- ISO-8601 UTC
    kind    TEXT NOT NULL,          -- 'thesis' | 'decision'
    payload TEXT NOT NULL           -- JSON
);
CREATE INDEX IF NOT EXISTS idx_memory_ticker ON memory (ticker, kind, ts);
"""


class MemoryStore:
    def __init__(self, path: str = "memory.db"):
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)

    def save_thesis(self, ticker: str, thesis: dict, ts: str | None = None) -> None:
        self._insert(ticker, THESIS, thesis, ts)

    def save_decision(self, ticker: str, decision: dict, ts: str | None = None) -> None:
        self._insert(ticker, DECISION, decision, ts)

    def get_theses(self, ticker: str) -> list[dict]:
        """All past theses for a ticker, oldest first. Each: {ts, payload}."""
        return self._query(ticker, THESIS)

    def get_decisions(self, ticker: str) -> list[dict]:
        return self._query(ticker, DECISION)

    def _insert(self, ticker: str, kind: str, payload: dict, ts: str | None) -> None:
        if not ticker:
            raise ValueError("ticker is required")
        ts = ts or datetime.now(timezone.utc).isoformat()
        self._db.execute(
            "INSERT INTO memory (ticker, ts, kind, payload) VALUES (?, ?, ?, ?)",
            (ticker, ts, kind, json.dumps(payload)),
        )
        self._db.commit()

    def _query(self, ticker: str, kind: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT ts, payload FROM memory WHERE ticker = ? AND kind = ? ORDER BY ts",
            (ticker, kind),
        ).fetchall()
        return [{"ts": r["ts"], "payload": json.loads(r["payload"])} for r in rows]

    def close(self) -> None:
        self._db.close()


if __name__ == "__main__":
    m = MemoryStore(":memory:")
    m.save_thesis("AAPL", {"call": "buy", "conf": 0.8}, ts="2026-01-01T00:00:00+00:00")
    m.save_thesis("AAPL", {"call": "hold", "conf": 0.5}, ts="2026-02-01T00:00:00+00:00")
    m.save_thesis("MSFT", {"call": "sell"})
    m.save_decision("AAPL", {"action": "buy", "size": 100})

    theses = m.get_theses("AAPL")
    assert len(theses) == 2, theses
    assert theses[0]["payload"]["call"] == "buy"      # oldest first
    assert theses[1]["payload"]["conf"] == 0.5
    assert m.get_theses("MSFT")[0]["payload"]["call"] == "sell"
    assert m.get_decisions("AAPL")[0]["payload"]["size"] == 100
    assert m.get_theses("NONE") == []
    try:
        m.save_thesis("", {})
        assert False, "empty ticker should raise"
    except ValueError:
        pass
    print("ok")
