"""Storage backends — Postgres if available, else JSONL in .gripe-mcp/."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


class Backend(Protocol):
    """Minimal storage interface."""

    def write(self, entry: dict[str, Any]) -> None: ...
    def read(self, since: str | None, min_severity: str | None) -> list[dict[str, Any]]: ...


# ── Severity ordering (for min_severity filter) ─────────────────────

_SEV_ORDER = {"low": 0, "medium": 1, "high": 2}


# ── JSONL backend ────────────────────────────────────────────────────

class JsonlBackend:
    """One JSONL file per day in data_dir."""

    def __init__(self, data_dir: str | Path | None = None):
        if data_dir is None:
            data_dir = Path.cwd() / ".gripe-mcp"
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def write(self, entry: dict[str, Any]) -> None:
        ts = entry.get("ts", datetime.now(timezone.utc).isoformat())
        day = ts[:10]  # YYYY-MM-DD
        path = self._dir / f"{day}.jsonl"
        with open(path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read(
        self, since: str | None = None, min_severity: str | None = None
    ) -> list[dict[str, Any]]:
        cutoff = _parse_since(since)
        min_sev = _SEV_ORDER.get(min_severity or "low", 0)
        results: list[dict[str, Any]] = []
        for path in sorted(self._dir.glob("*.jsonl"), reverse=True):
            # Quick date check from filename
            day_str = path.stem  # YYYY-MM-DD
            if cutoff and day_str < cutoff[:10]:
                break
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    if cutoff and entry.get("ts", "") < cutoff:
                        continue
                    sev = _SEV_ORDER.get(entry.get("severity", "low"), 0)
                    if sev < min_sev:
                        continue
                    results.append(entry)
        results.sort(key=lambda e: e.get("ts", ""), reverse=True)
        return results


# ── Postgres backend ─────────────────────────────────────────────────

class PostgresBackend:
    """Single table in Postgres."""

    DDL = """\
    CREATE TABLE IF NOT EXISTS gripe_issues (
        id          SERIAL PRIMARY KEY,
        ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
        agent_id    TEXT,
        task_id     TEXT,
        severity    TEXT NOT NULL DEFAULT 'low',
        section     TEXT,
        mode        TEXT,
        description TEXT,
        raw         JSONB
    );
    """

    def __init__(self, dsn: str):
        import psycopg

        self._dsn = dsn
        with psycopg.connect(dsn) as conn:
            conn.execute(self.DDL)
            conn.commit()

    def write(self, entry: dict[str, Any]) -> None:
        import psycopg
        from psycopg.types.json import Jsonb

        with psycopg.connect(self._dsn) as conn:
            conn.execute(
                """INSERT INTO gripe_issues
                   (ts, agent_id, task_id, severity, section, mode, description, raw)
                   VALUES (%(ts)s, %(agent_id)s, %(task_id)s, %(severity)s,
                           %(section)s, %(mode)s, %(description)s, %(raw)s)""",
                {
                    "ts": entry.get("ts", datetime.now(timezone.utc).isoformat()),
                    "agent_id": entry.get("agent_id"),
                    "task_id": entry.get("task_id"),
                    "severity": entry.get("severity", "low"),
                    "section": entry.get("section"),
                    "mode": entry.get("mode"),
                    "description": entry.get("description"),
                    "raw": Jsonb(entry),
                },
            )
            conn.commit()

    def read(
        self, since: str | None = None, min_severity: str | None = None
    ) -> list[dict[str, Any]]:
        import psycopg

        clauses = ["1=1"]
        params: dict[str, Any] = {}
        if since:
            cutoff = _parse_since(since)
            if cutoff:
                clauses.append("ts >= %(cutoff)s")
                params["cutoff"] = cutoff
        if min_severity and min_severity in _SEV_ORDER:
            ok = [k for k, v in _SEV_ORDER.items() if v >= _SEV_ORDER[min_severity]]
            clauses.append("severity = ANY(%(sevs)s)")
            params["sevs"] = ok

        sql = (
            f"SELECT raw FROM gripe_issues WHERE {' AND '.join(clauses)} "
            "ORDER BY ts DESC LIMIT 200"
        )
        with psycopg.connect(self._dsn) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [r[0] for r in rows]


# ── Helpers ──────────────────────────────────────────────────────────

def _parse_since(since: str | None) -> str | None:
    """Convert relative durations (7d, 30d) or ISO dates to ISO string."""
    if not since:
        return None
    since = since.strip()
    # Relative: "7d", "30d"
    if since.endswith("d") and since[:-1].isdigit():
        from datetime import timedelta

        days = int(since[:-1])
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return cutoff.isoformat()
    # Assume ISO date or datetime
    return since


def get_backend() -> Backend:
    """Pick backend based on GRIPE_DB_URL env var."""
    dsn = os.environ.get("GRIPE_DB_URL", "")
    if dsn:
        try:
            return PostgresBackend(dsn)
        except Exception:
            pass  # fall through to JSONL
    return JsonlBackend()
