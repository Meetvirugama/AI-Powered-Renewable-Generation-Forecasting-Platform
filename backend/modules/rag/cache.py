"""TTL response cache for copilot answers.

In-process dict by default. Keyed on the semantic inputs, so the same question
asked under a different rule year, or against a different penalty, is correctly a
different entry -- a cache that ignored `engine_context` would happily serve an
explanation of yesterday's penalty for today's number.

This cache is the main defence against Groq's free-tier rate limit during a demo,
where four teammates and a judge can be querying at once.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time

MAX_ENTRIES = 2000
_EVICT_TO = 1500

_store: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()
_hits = 0
_misses = 0


def ttl_seconds() -> int:
    try:
        return int(os.getenv("RAG_CACHE_TTL_SECONDS", 3600))
    except (TypeError, ValueError):
        return 3600


def make_key(question: str, rule_year, engine_context: dict | None) -> str:
    payload = {
        "q": " ".join((question or "").lower().split()),
        "y": rule_year,
        # Round engine floats so sub-decimal jitter between runs does not
        # needlessly blow the cache on what is the same block.
        "e": {
            k: (round(v, 1) if isinstance(v, float) else v)
            for k, v in sorted((engine_context or {}).items())
        },
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:32]


def get(key: str) -> dict | None:
    global _hits, _misses
    with _lock:
        entry = _store.get(key)
        if not entry:
            _misses += 1
            return None
        stored_at, value = entry
        if time.time() - stored_at > ttl_seconds():
            _store.pop(key, None)
            _misses += 1
            return None
        _hits += 1
        return dict(value)


def put(key: str, value: dict) -> None:
    with _lock:
        if len(_store) >= MAX_ENTRIES:
            # Oldest-first eviction, in one pass rather than per insert.
            for k, _ in sorted(_store.items(), key=lambda kv: kv[1][0])[: MAX_ENTRIES - _EVICT_TO]:
                _store.pop(k, None)
        _store[key] = (time.time(), dict(value))


def clear() -> None:
    global _hits, _misses
    with _lock:
        _store.clear()
        _hits = _misses = 0


def stats() -> dict:
    with _lock:
        total = _hits + _misses
        return {
            "entries": len(_store),
            "ttl_s": ttl_seconds(),
            "hits": _hits,
            "misses": _misses,
            "hit_rate": round(_hits / total, 3) if total else 0.0,
        }
