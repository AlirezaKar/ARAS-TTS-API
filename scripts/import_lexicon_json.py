"""Import flat lexicon.json into SQLite pronunciation DB.

Usage:
  python scripts/import_lexicon_json.py
  python scripts/import_lexicon_json.py --json fine_tuning/lexicon.json --db fine_tuning/pronunciation.db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.services.pronunciation.db import import_json_lexicon, init_schema  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Import lexicon.json into pronunciation SQLite DB")
    parser.add_argument(
        "--json",
        type=Path,
        default=settings.lexicon_path,
        help="Source flat JSON lexicon",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=settings.pronunciation_db_path,
        help="Destination SQLite path",
    )
    args = parser.parse_args()

    json_path = args.json if args.json.is_absolute() else ROOT / args.json
    db_path = args.db if args.db.is_absolute() else ROOT / args.db

    if not json_path.exists():
        print(f"Missing lexicon JSON: {json_path}")
        return 1

    init_schema(db_path)
    n = import_json_lexicon(db_path, json_path)
    print(f"Imported/updated {n} lexicon entries into {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
