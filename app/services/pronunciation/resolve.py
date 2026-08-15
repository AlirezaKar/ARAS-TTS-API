"""Context-aware Persian pronunciation resolution (POS + SQLite lexicon)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from app.core.config import settings
from app.services.fine_tune import (
    ALLOWED_HARAKAT,
    strip_harakat,
    validate_diacritized,
)
from app.services.pronunciation.db import lookup_lexicon

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+")
_HARAKAT_RE = re.compile("[" + "".join(ALLOWED_HARAKAT) + "]")

_tagger = None
_tagger_failed = False


def _get_tagger():
    global _tagger, _tagger_failed
    if _tagger_failed:
        return None
    if _tagger is not None:
        return _tagger
    try:
        from hazm import POSTagger, word_tokenize

        # hazm 0.7+ uses model path; older APIs differ — try common patterns
        try:
            tagger = POSTagger(model="pos_tagger.model")
        except TypeError:
            tagger = POSTagger()
        _tagger = (tagger, word_tokenize)
        return _tagger
    except Exception as exc:  # noqa: BLE001
        logger.warning("hazm POS tagger unavailable (%s); using null context tags", exc)
        _tagger_failed = True
        return None


def tag_sentence(text: str) -> list[tuple[str, str | None]]:
    """
    Return list of (surface_word, pos_tag_or_None) for Persian tokens in order.
    Falls back to untagged word list if hazm is unavailable.
    """
    bundle = _get_tagger()
    if bundle is None:
        return [(m.group(0), None) for m in _WORD_RE.finditer(text)]

    tagger, word_tokenize = bundle
    try:
        tokens = word_tokenize(text)
        tagged = tagger.tag(tokens)
        out: list[tuple[str, str | None]] = []
        for tok, pos in tagged:
            if _WORD_RE.fullmatch(tok) or _HARAKAT_RE.sub("", tok) and any(
                "\u0600" <= c <= "\u06FF" for c in tok
            ):
                bare_pos = str(pos).split(",")[0].strip() if pos else None
                # Normalize hazm tags to coarse labels when possible
                coarse = _coarse_pos(bare_pos) if bare_pos else None
                out.append((tok, coarse))
        if out:
            return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("hazm tagging failed (%s); falling back", exc)

    return [(m.group(0), None) for m in _WORD_RE.finditer(text)]


def _coarse_pos(tag: str) -> str:
    t = tag.upper()
    if t.startswith("N") or "NOUN" in t:
        return "N"
    if t.startswith("V") or "VERB" in t:
        return "V"
    if t.startswith("AJ") or "ADJ" in t:
        return "AJ"
    if t.startswith("ADV"):
        return "ADV"
    if t.startswith("P") and "PRON" not in t:
        return "P"
    return tag


def resolve_pronunciation(
    word: str,
    sentence_context: str = "",
    pos: str | None = None,
    *,
    db_path: Path | None = None,
    special_words: dict[str, str] | None = None,
) -> str:
    """
    Resolve diacritized form for a word.

    Order: special_words → (word, pos) → (word, NULL) → original word.
    """
    bare = strip_harakat(word.strip())
    if not bare:
        return word

    if special_words:
        for k, v in special_words.items():
            if strip_harakat(k.strip()) == bare:
                return validate_diacritized(v.strip())

    path = db_path or settings.pronunciation_db_path
    if pos is None and sentence_context:
        for tok, tok_pos in tag_sentence(sentence_context):
            if strip_harakat(tok) == bare:
                pos = tok_pos
                break

    found = lookup_lexicon(path, bare, context_tag=pos)
    if found:
        return found
    return word


def diacritize_text(
    text: str,
    special_words: dict[str, str] | None = None,
    *,
    db_path: Path | None = None,
) -> str:
    """Apply lexicon (and special_words) to all Persian words in text with POS context."""
    path = db_path or settings.pronunciation_db_path
    tagged = tag_sentence(text)

    # Build bare → replacement using first matching tagged occurrence's POS
    # Then replace left-to-right via regex using per-match POS from tagged list.
    special = {
        strip_harakat(k.strip()): validate_diacritized(v.strip())
        for k, v in (special_words or {}).items()
        if strip_harakat(k.strip())
    }

    # Queue of (bare, pos) in document order for sequential consume
    queue = [(strip_harakat(tok), pos) for tok, pos in tagged]
    idx = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal idx
        word = match.group(0)
        bare = strip_harakat(word)
        pos: str | None = None
        # Align with tagged queue
        while idx < len(queue) and queue[idx][0] != bare:
            idx += 1
        if idx < len(queue) and queue[idx][0] == bare:
            pos = queue[idx][1]
            idx += 1

        if bare in special:
            return special[bare]
        found = lookup_lexicon(path, bare, context_tag=pos)
        return found if found else word

    return _WORD_RE.sub(repl, text)
