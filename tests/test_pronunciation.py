"""Tests for SQLite lexicon lookup, homographs, and feedback safety."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.fine_tune import fine_tune_text, strip_harakat
from app.services.pronunciation.db import (
    count_lexicon,
    get_pending,
    init_schema,
    insert_pending,
    lookup_lexicon,
    upsert_lexicon,
)
from app.services.pronunciation.resolve import diacritize_text, resolve_pronunciation


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "pronunciation.db"
    init_schema(path)
    return path


def test_import_null_context_lookup(db_path: Path) -> None:
    upsert_lexicon(
        db_path,
        word="کلمه",
        harakat="کَلَمِه",
        context_tag=None,
        source="manual",
        confidence=1.0,
    )
    assert lookup_lexicon(db_path, "کلمه", context_tag=None) == "کَلَمِه"
    # POS miss still falls back to NULL-context entry
    assert lookup_lexicon(db_path, "کلمه", context_tag="N") == "کَلَمِه"


def test_homograph_pos_vs_null(db_path: Path) -> None:
    """Same spelling, different pronunciations by context_tag."""
    # شیر as noun (milk) vs verb-ish/other (lion) — illustrative harakat forms
    upsert_lexicon(
        db_path,
        word="شیر",
        harakat="شِیر",  # milk-ish
        context_tag="N",
        source="manual",
        confidence=1.0,
    )
    upsert_lexicon(
        db_path,
        word="شیر",
        harakat="شَیر",  # alternate
        context_tag="V",
        source="manual",
        confidence=1.0,
    )
    upsert_lexicon(
        db_path,
        word="شیر",
        harakat="شیر",  # bare default
        context_tag=None,
        source="manual",
        confidence=1.0,
    )

    assert lookup_lexicon(db_path, "شیر", "N") == "شِیر"
    assert lookup_lexicon(db_path, "شیر", "V") == "شَیر"
    assert lookup_lexicon(db_path, "شیر", None) == "شیر"

    assert (
        resolve_pronunciation("شیر", pos="N", db_path=db_path) == "شِیر"
    )
    assert (
        resolve_pronunciation("شیر", pos="V", db_path=db_path) == "شَیر"
    )
    assert resolve_pronunciation("شیر", pos=None, db_path=db_path) == "شیر"

    # special_words win over lexicon
    assert (
        resolve_pronunciation(
            "شیر",
            pos="N",
            db_path=db_path,
            special_words={"شیر": "شیری"},
        )
        == "شیری"
    )


def test_diacritize_uses_null_entries(db_path: Path) -> None:
    upsert_lexicon(db_path, word="سلام", harakat="سَلام", context_tag=None)
    out = diacritize_text("سلام دنیا", db_path=db_path)
    assert "سَلام" in out


def test_feedback_does_not_mutate_lexicon(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    upsert_lexicon(db_path, word="کفش", harakat="کَفش", context_tag=None)
    before = count_lexicon(db_path)
    before_val = lookup_lexicon(db_path, "کفش")

    monkeypatch.setattr(
        "app.core.config.settings.pronunciation_db_path",
        db_path,
    )
    # Avoid loading full app settings side-effects from other modules if needed
    from app.main import app

    client = TestClient(app)
    # Force routes to use our temp DB (startup already ran; patch before call)
    monkeypatch.setattr(
        "app.api.routes.settings.pronunciation_db_path",
        db_path,
    )

    resp = client.post(
        "/feedback",
        json={
            "word": "کفش",
            "correct_harakat": "کِفش",
            "context": "این کفش نو است",
            "text_id": "test-job-1",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    pending_id = body["pending_id"]

    assert count_lexicon(db_path) == before
    assert lookup_lexicon(db_path, "کفش") == before_val

    pending = get_pending(db_path, pending_id)
    assert pending is not None
    assert pending["word"] == "کفش"
    assert pending["proposed_harakat"] == "کِفش"
    assert pending["source"] == "user_report"
    assert pending["confidence"] == 0.9
    assert pending["promoted_at"] is None


def test_insert_pending_direct(db_path: Path) -> None:
    pid = insert_pending(
        db_path,
        word="متن",
        proposed_harakat="مَتْن",
        source="user_report",
        confidence=0.9,
    )
    row = get_pending(db_path, pid)
    assert row is not None
    assert strip_harakat(row["proposed_harakat"]) == "متن"
    assert count_lexicon(db_path) == 0


def test_fine_tune_bootstrap_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty DB falls back to JSON seed path."""
    db = tmp_path / "empty.db"
    init_schema(db)
    json_path = tmp_path / "lex.json"
    json_path.write_text('{"سلام": "سَلام"}', encoding="utf-8")
    monkeypatch.setattr("app.core.config.settings.pronunciation_db_path", db)
    tuned = fine_tune_text("سلام", lexicon_path=json_path)
    assert "سَلام" in tuned
