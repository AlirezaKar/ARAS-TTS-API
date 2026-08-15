"""Pronunciation lexicon storage (SQLite). Live lexicon writes only via import/admin."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Iterator

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS lexicon (
    id INTEGER PRIMARY KEY,
    word TEXT NOT NULL,
    harakat TEXT NOT NULL,
    context_tag TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_lexicon_word_context
ON lexicon (word, COALESCE(context_tag, ''));

CREATE INDEX IF NOT EXISTS ix_lexicon_word ON lexicon (word);

CREATE TABLE IF NOT EXISTS pending_corrections (
    id INTEGER PRIMARY KEY,
    text_id TEXT,
    word TEXT NOT NULL,
    proposed_harakat TEXT NOT NULL,
    context TEXT,
    context_tag TEXT,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    detection_method TEXT NOT NULL,
    created_at TEXT NOT NULL,
    promoted_at TEXT
);

CREATE INDEX IF NOT EXISTS ix_pending_word ON pending_corrections (word);

CREATE TABLE IF NOT EXISTS promotion_log (
    id INTEGER PRIMARY KEY,
    pending_id INTEGER,
    lexicon_id INTEGER,
    word TEXT NOT NULL,
    before_harakat TEXT,
    after_harakat TEXT NOT NULL,
    context_tag TEXT,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_connection(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(db_path: Path) -> None:
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA_SQL)


def upsert_lexicon(
    db_path: Path,
    *,
    word: str,
    harakat: str,
    context_tag: str | None = None,
    source: str = "manual",
    confidence: float = 1.0,
) -> int:
    now = _utcnow()
    with get_connection(db_path) as conn:
        existing = conn.execute(
            """
            SELECT id FROM lexicon
            WHERE word = ? AND COALESCE(context_tag, '') = COALESCE(?, '')
            """,
            (word, context_tag),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE lexicon
                SET harakat = ?, source = ?, confidence = ?, updated_at = ?, is_active = 1
                WHERE id = ?
                """,
                (harakat, source, confidence, now, existing["id"]),
            )
            return int(existing["id"])
        cur = conn.execute(
            """
            INSERT INTO lexicon (
                word, harakat, context_tag, source, confidence, created_at, updated_at, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (word, harakat, context_tag, source, confidence, now, now),
        )
        return int(cur.lastrowid)


def lookup_lexicon(
    db_path: Path,
    word: str,
    context_tag: str | None = None,
) -> str | None:
    """Exact (word, context_tag) then (word, NULL) fallback. Returns harakat or None."""
    with get_connection(db_path) as conn:
        if context_tag is not None:
            row = conn.execute(
                """
                SELECT harakat FROM lexicon
                WHERE is_active = 1 AND word = ? AND context_tag = ?
                LIMIT 1
                """,
                (word, context_tag),
            ).fetchone()
            if row:
                return str(row["harakat"])
        row = conn.execute(
            """
            SELECT harakat FROM lexicon
            WHERE is_active = 1 AND word = ? AND context_tag IS NULL
            LIMIT 1
            """,
            (word,),
        ).fetchone()
        if row:
            return str(row["harakat"])
        # Any active row for word if no NULL-context entry
        row = conn.execute(
            """
            SELECT harakat FROM lexicon
            WHERE is_active = 1 AND word = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (word,),
        ).fetchone()
        return str(row["harakat"]) if row else None


def count_lexicon(db_path: Path) -> int:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM lexicon WHERE is_active = 1"
        ).fetchone()
        return int(row["n"])


def insert_pending(
    db_path: Path,
    *,
    word: str,
    proposed_harakat: str,
    source: str = "user_report",
    confidence: float = 0.9,
    detection_method: str = "user_feedback",
    text_id: str | None = None,
    context: str | None = None,
    context_tag: str | None = None,
) -> int:
    now = _utcnow()
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO pending_corrections (
                text_id, word, proposed_harakat, context, context_tag,
                source, confidence, detection_method, created_at, promoted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                text_id,
                word,
                proposed_harakat,
                context,
                context_tag,
                source,
                confidence,
                detection_method,
                now,
            ),
        )
        return int(cur.lastrowid)


def get_pending(db_path: Path, pending_id: int) -> dict[str, Any] | None:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM pending_corrections WHERE id = ?",
            (pending_id,),
        ).fetchone()
        return dict(row) if row else None


def iter_lexicon(db_path: Path) -> Iterator[dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM lexicon WHERE is_active = 1 ORDER BY id"
        ).fetchall()
        for row in rows:
            yield dict(row)


def import_json_lexicon(
    db_path: Path,
    json_path: Path,
    *,
    source: str = "manual",
    confidence: float = 1.0,
) -> int:
    """Import flat word→harakat JSON. Returns number of upserted rows."""
    import json

    from app.services.fine_tune import strip_harakat, validate_diacritized

    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Lexicon JSON must be an object")
    init_schema(db_path)
    n = 0
    for key, value in data.items():
        bare = strip_harakat(str(key).strip())
        if not bare:
            continue
        upsert_lexicon(
            db_path,
            word=bare,
            harakat=validate_diacritized(str(value).strip()),
            context_tag=None,
            source=source,
            confidence=confidence,
        )
        n += 1
    return n
