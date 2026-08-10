"""Quick end-to-end TTS test: submit sample, poll, open audio in default player.

Examples:
  test_tts.cmd
  test_tts.cmd --accuracy balanced
  test_tts.cmd --accuracy premium --elevenlabs-model v3
  test_tts.cmd --accuracy high --no-open
  test_tts.cmd --all
  test_tts.cmd --file samples\\hello.txt --accuracy premium --format wav
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]  # project root (not scripts/)
BASE = os.environ.get("TTS_API_BASE", "http://127.0.0.1:8000")
DEFAULT_SAMPLE = ROOT / "samples" / "hello.txt"
ACCURACIES = ("fast", "balanced", "high", "premium")
ELEVENLABS_MODELS = ("v1", "v2", "v3")


def run_one(
    *,
    accuracy: str,
    sample: Path,
    audio_format: str,
    open_player: bool,
    elevenlabs_model: str | None = None,
) -> int:
    special = {"کلمه": "کَلِمَه", "کفش": "کَفش"}
    print(
        f"\n=== accuracy={accuracy} format={audio_format} "
        f"elevenlabs_model={elevenlabs_model or '-'} file={sample.name} ==="
    )
    data = {
        "phone_number": "09120000000",
        "platform": "bale",
        "accuracy": accuracy,
        "audio_format": audio_format,
        "special_words": json.dumps(special, ensure_ascii=False),
    }
    if accuracy == "premium" and elevenlabs_model:
        data["elevenlabs_model"] = elevenlabs_model
    with sample.open("rb") as f:
        resp = httpx.post(
            f"{BASE}/tts",
            data=data,
            files={"file": (sample.name, f, "text/plain")},
            timeout=60,
        )
    print("submit:", resp.status_code, resp.text)
    resp.raise_for_status()
    job_id = resp.json()["job_id"]

    for _ in range(90):
        job = httpx.get(f"{BASE}/jobs/{job_id}", timeout=30).json()
        print(
            f"  status={job.get('status')} stage={job.get('stage')} "
            f"engine={job.get('engine')} error={job.get('error')}"
        )
        if job.get("status") in ("completed", "failed"):
            print(json.dumps(job, ensure_ascii=False, indent=2))
            audio_url = job.get("audio_url")
            if not audio_url:
                return 1 if job.get("status") == "failed" else 0
            name = audio_url.rsplit("/", 1)[-1]
            out = ROOT / "output" / "audio" / name
            if not out.exists():
                audio = httpx.get(f"{BASE}/files/{name}", timeout=60)
                audio.raise_for_status()
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(audio.content)
            print(f"AUDIO FILE: {out}")
            if open_player and sys.platform.startswith("win"):
                os.startfile(str(out))  # noqa: S606
            elif open_player:
                print("Open that file in any audio player.")
            return 0 if job.get("status") == "completed" else 1
        time.sleep(1.5)

    print("timeout waiting for job")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Persian TTS-API")
    parser.add_argument(
        "--accuracy",
        "-a",
        choices=ACCURACIES,
        default="fast",
        help="Accuracy tier (selects preferred engine). Default: fast",
    )
    parser.add_argument(
        "--elevenlabs-model",
        choices=ELEVENLABS_MODELS,
        default="v2",
        help="ElevenLabs model when accuracy=premium: v1=flash, v2=multilingual, v3=eleven_v3",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run once for every accuracy tier (fast → premium)",
    )
    parser.add_argument(
        "--file",
        "-f",
        type=Path,
        default=DEFAULT_SAMPLE,
        help=f"Input text/pdf/docx (default: {DEFAULT_SAMPLE})",
    )
    parser.add_argument(
        "--format",
        choices=("wav", "mp3"),
        default="wav",
        dest="audio_format",
        help="Audio format (default: wav)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the WAV/MP3 in the default player",
    )
    args = parser.parse_args()

    sample = args.file if args.file.is_absolute() else (ROOT / args.file)
    if not sample.exists():
        print(f"Missing sample: {sample}")
        return 1

    print(f"API: {BASE}")
    try:
        health = httpx.get(f"{BASE}/health", timeout=5)
        health.raise_for_status()
        print("health:", health.json())
    except Exception as exc:  # noqa: BLE001
        print(f"API not reachable. Start with run_api.cmd first.\n{exc}")
        return 1

    engines = httpx.get(f"{BASE}/engines", timeout=10).json()
    print("engines:", json.dumps(engines, ensure_ascii=False, indent=2))

    tiers = list(ACCURACIES) if args.all else [args.accuracy]
    open_player = not args.no_open
    worst = 0
    for i, accuracy in enumerate(tiers):
        is_last = i == len(tiers) - 1
        code = run_one(
            accuracy=accuracy,
            sample=sample,
            audio_format=args.audio_format,
            open_player=open_player and (is_last or not args.all),
            elevenlabs_model=args.elevenlabs_model,
        )
        worst = max(worst, code)
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
