"""Pronunciation package: SQLite lexicon + context-aware diacritization."""

from app.services.pronunciation.db import init_schema, insert_pending, lookup_lexicon
from app.services.pronunciation.resolve import diacritize_text, resolve_pronunciation

__all__ = [
    "diacritize_text",
    "init_schema",
    "insert_pending",
    "lookup_lexicon",
    "resolve_pronunciation",
]
