import re
import time
from contextlib import contextmanager

from flask import g, has_request_context


_SERVER_TIMING_TOKEN_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _ensure_perf_spans():
    if not has_request_context():
        return []
    spans = getattr(g, "perf_spans", None)
    if spans is None:
        spans = []
        g.perf_spans = spans
    return spans


def sanitize_server_timing_name(name: str) -> str:
    raw = (name or "").strip().lower()
    normalized = _SERVER_TIMING_TOKEN_RE.sub("-", raw).strip("-")
    return normalized or "app"


def add_perf_span(name: str, duration_ms: float) -> None:
    if not has_request_context():
        return
    _ensure_perf_spans().append(
        {
            "name": sanitize_server_timing_name(name),
            "duration_ms": max(0.0, float(duration_ms or 0.0)),
        }
    )


@contextmanager
def perf_section(name: str):
    started_at = time.perf_counter()
    try:
        yield
    finally:
        add_perf_span(name, (time.perf_counter() - started_at) * 1000)
