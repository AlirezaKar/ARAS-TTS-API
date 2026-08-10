"""Persian harakat fine-tuning: special-word lexicon + Unicode diacritics."""

from __future__ import annotations

import json
import re
from pathlib import Path

# Short-vowel / sukun combining marks used for Persian pronunciation hints
FATHA = "\u064e"  # َ
KASRA = "\u0650"  # ِ
DAMMA = "\u064f"  # ُ
SUKUN = "\u0652"  # ْ

ALLOWED_HARAKAT = frozenset(
    {
        FATHA,
        KASRA,
        DAMMA,
        SUKUN,
        "\u064b",  # tanwin fath
        "\u064c",  # tanwin damm
        "\u064d",  # tanwin kasr
        "\u0651",  # shadda
        "\u0670",  # superscript alef
    }
)

# Strip harakat when matching bare words in the lexicon keys
_HARAKAT_RE = re.compile("[" + "".join(ALLOWED_HARAKAT) + "]")
_WORD_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+")


def strip_harakat(text: str) -> str:
    return _HARAKAT_RE.sub("", text)


def validate_diacritized(value: str) -> str:
    """Keep letters + allowed harakat; drop other combining junk."""
    out: list[str] = []
    for ch in value:
        if ch in ALLOWED_HARAKAT:
            out.append(ch)
        elif ord(ch) < 0x0300 or ord(ch) > 0x036F:
            # keep non-combining (letters, punctuation already filtered by caller)
            out.append(ch)
        # else drop unexpected combining marks
    return "".join(out)


def load_lexicon(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Lexicon must be a JSON object of word -> diacritized form")
    return {str(k): validate_diacritized(str(v)) for k, v in data.items()}


def merge_lexicons(*maps: dict[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for m in maps:
        for k, v in m.items():
            bare = strip_harakat(k.strip())
            if bare:
                merged[bare] = validate_diacritized(v.strip())
    return merged


def apply_special_words(text: str, special_words: dict[str, str]) -> str:
    """
    Replace whole Persian words using the lexicon.
    Longer keys win first. Existing harakat in the source are preserved
    for words that are not overridden by the lexicon.
    """
    if not special_words:
        return text

    # Sort by bare-key length descending
    items = sorted(
        ((strip_harakat(k), validate_diacritized(v)) for k, v in special_words.items()),
        key=lambda kv: len(kv[0]),
        reverse=True,
    )
    lookup = {k: v for k, v in items if k}

    def repl(match: re.Match[str]) -> str:
        word = match.group(0)
        bare = strip_harakat(word)
        if bare in lookup:
            return lookup[bare]
        return word

    return _WORD_RE.sub(repl, text)


def fine_tune_text(
    text: str,
    special_words: dict[str, str] | None = None,
    lexicon_path: Path | None = None,
) -> str:
    base: dict[str, str] = {}
    if lexicon_path is not None:
        base = load_lexicon(lexicon_path)
    merged = merge_lexicons(base, special_words or {})
    return apply_special_words(text, merged)
