"""Tests for gripe-mcp — JSONL backend + server tool."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from gripe.storage import JsonlBackend, _parse_since


# ── _parse_since ─────────────────────────────────────────────────────

def test_parse_since_none():
    assert _parse_since(None) is None


def test_parse_since_empty():
    assert _parse_since("") is None


def test_parse_since_relative_days():
    result = _parse_since("7d")
    assert result is not None
    # Should be a valid ISO timestamp roughly 7 days ago
    dt = datetime.fromisoformat(result)
    delta = datetime.now(timezone.utc) - dt
    assert 6.9 < delta.total_seconds() / 86400 < 7.1


def test_parse_since_iso_passthrough():
    iso = "2026-03-01T00:00:00+00:00"
    assert _parse_since(iso) == iso


# ── JsonlBackend ─────────────────────────────────────────────────────

@pytest.fixture
def jsonl_dir(tmp_path):
    return tmp_path / "gripe"


@pytest.fixture
def backend(jsonl_dir):
    return JsonlBackend(data_dir=jsonl_dir)


def _make_entry(desc: str, severity: str = "low", mode: str = "other", **kw):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent_id": "test-agent",
        "task_id": "test-task",
        "severity": severity,
        "section": "test section",
        "mode": mode,
        "description": desc,
    }
    entry.update(kw)
    return entry


def test_write_creates_file(backend, jsonl_dir):
    entry = _make_entry("something broke")
    backend.write(entry)
    files = list(jsonl_dir.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["description"] == "something broke"


def test_write_appends(backend, jsonl_dir):
    backend.write(_make_entry("first"))
    backend.write(_make_entry("second"))
    files = list(jsonl_dir.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().strip().split("\n")
    assert len(lines) == 2


def test_read_all(backend):
    backend.write(_make_entry("a", severity="low"))
    backend.write(_make_entry("b", severity="high"))
    results = backend.read()
    assert len(results) == 2


def test_read_min_severity(backend):
    backend.write(_make_entry("low one", severity="low"))
    backend.write(_make_entry("med one", severity="medium"))
    backend.write(_make_entry("high one", severity="high"))
    results = backend.read(min_severity="medium")
    assert len(results) == 2
    descs = {r["description"] for r in results}
    assert "low one" not in descs
    assert "med one" in descs
    assert "high one" in descs


def test_read_min_severity_high(backend):
    backend.write(_make_entry("low", severity="low"))
    backend.write(_make_entry("high", severity="high"))
    results = backend.read(min_severity="high")
    assert len(results) == 1
    assert results[0]["description"] == "high"


# ── Server tool ──────────────────────────────────────────────────────

def test_report_issue_returns_logged(tmp_path):
    """The report_issue tool should return 'logged' and write to JSONL."""
    # Patch backend before importing server (which caches at module level)
    jsonl_backend = JsonlBackend(data_dir=tmp_path / "gripe")

    import gripe.server as srv

    srv._backend = jsonl_backend

    result = srv.report_issue(
        description="tool doc says max 200 but rejects at 150",
        severity="medium",
        section="put tool",
        mode="bad_tool_doc",
    )
    assert result == "logged"

    entries = jsonl_backend.read()
    assert len(entries) == 1
    assert entries[0]["mode"] == "bad_tool_doc"
    assert entries[0]["severity"] == "medium"

    # Cleanup
    srv._backend = None


def test_report_issue_truncates(tmp_path):
    jsonl_backend = JsonlBackend(data_dir=tmp_path / "gripe")

    import gripe.server as srv

    srv._backend = jsonl_backend

    long_desc = "x" * 300
    long_section = "y" * 100
    srv.report_issue(description=long_desc, section=long_section)

    entries = jsonl_backend.read()
    assert len(entries[0]["description"]) == 200
    assert len(entries[0]["section"]) == 80

    srv._backend = None


def test_report_issue_invalid_severity(tmp_path):
    jsonl_backend = JsonlBackend(data_dir=tmp_path / "gripe")

    import gripe.server as srv

    srv._backend = jsonl_backend

    srv.report_issue(description="test", severity="critical")

    entries = jsonl_backend.read()
    assert entries[0]["severity"] == "low"  # falls back

    srv._backend = None


def test_report_issue_invalid_mode(tmp_path):
    jsonl_backend = JsonlBackend(data_dir=tmp_path / "gripe")

    import gripe.server as srv

    srv._backend = jsonl_backend

    srv.report_issue(description="test", mode="nonexistent")

    entries = jsonl_backend.read()
    assert entries[0]["mode"] == "other"  # falls back

    srv._backend = None


def test_agent_id_from_env(tmp_path):
    jsonl_backend = JsonlBackend(data_dir=tmp_path / "gripe")

    import gripe.server as srv

    srv._backend = jsonl_backend
    old = srv._AGENT_ID
    srv._AGENT_ID = "precis"

    srv.report_issue(description="test")
    entries = jsonl_backend.read()
    assert entries[0]["agent_id"] == "precis"

    srv._AGENT_ID = old
    srv._backend = None
