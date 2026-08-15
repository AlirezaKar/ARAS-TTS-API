"""
Simple test CLI for Persian TTS-API.

Usage:
  python -m cli.toolbox
  toolbox.cmd

Esc (or typing b / back) goes back / cancels the current prompt.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "http://127.0.0.1:5004"
SAMPLES = ROOT / "samples"

# Sentinel: user pressed Esc / asked to go back
BACK = object()


def banner() -> None:
    print(
        r"""
╔══════════════════════════════════════════╗
║       Persian TTS-API Test Toolbox       ║
╚══════════════════════════════════════════╝
"""
    )


def menu() -> None:
    print(
        """
  1) Health check
  2) List models
  3) Test TTS
  4) Import lexicon.json → SQLite DB
  0) Exit

"""
    )


def prompt_line(message: str, *, default: str | None = None) -> str | object:
    """
    Read a line. Returns BACK on Esc / 'b' / 'back'.
    On Windows, Esc is detected via msvcrt; elsewhere type b/back.
    """
    suffix = f" [{default}]" if default is not None else ""
    full = f"{message}{suffix}: "

    if sys.platform.startswith("win"):
        try:
            import msvcrt
        except ImportError:
            msvcrt = None  # type: ignore[assignment]
        if msvcrt is not None:
            print(full, end="", flush=True)
            buf: list[str] = []
            while True:
                ch = msvcrt.getwch()
                if ch in ("\x00", "\xe0"):
                    msvcrt.getwch()  # swallow special key trail
                    continue
                if ch == "\x1b":  # Esc
                    print()
                    return BACK
                if ch in ("\r", "\n"):
                    print()
                    text = "".join(buf).strip()
                    if not text and default is not None:
                        return default
                    if text.lower() in {"b", "back"}:
                        return BACK
                    return text
                if ch in ("\b", "\x08"):
                    if buf:
                        buf.pop()
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                    continue
                if ch == "\x03":  # Ctrl+C
                    raise KeyboardInterrupt
                buf.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()

    # Fallback (non-Windows or no msvcrt)
    try:
        raw = input(full)
    except EOFError:
        return BACK
    text = raw.strip()
    if not text and default is not None:
        return default
    if text.lower() in {"b", "back", "esc"}:
        return BACK
    return text


def pause() -> None:
    result = prompt_line("Press Enter to continue (Esc=menu)", default="")
    if result is BACK:
        return


def pretty(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def import_lexicon() -> None:
    """Run scripts/import_lexicon_json.py against the project seed JSON."""
    from app.core.config import settings
    from app.services.pronunciation.db import import_json_lexicon, init_schema

    json_path = settings.lexicon_path
    db_path = settings.pronunciation_db_path
    print(f"\nSource: {json_path}")
    print(f"Target: {db_path}")
    if not json_path.exists():
        print(f"✗ Missing {json_path}")
        return
    init_schema(db_path)
    n = import_json_lexicon(db_path, json_path)
    print(f"✓ Imported/updated {n} lexicon entries")
    print("  Edit fine_tuning\\lexicon.json, then run this again to apply changes.")


def health(client: httpx.Client) -> None:
    r = client.get("/health")
    r.raise_for_status()
    print("\n✓ Health")
    pretty(r.json())


def list_engines(client: httpx.Client) -> None:
    r = client.get("/engines")
    r.raise_for_status()
    engines = r.json().get("engines", [])
    print("\n┌────┬────────────────────────────┬───────────┬──────────────────────────────────────┐")
    print("│ #  │ Engine                     │ Available │ Versions / detail                    │")
    print("├────┼────────────────────────────┼───────────┼──────────────────────────────────────┤")
    for i, e in enumerate(engines, 1):
        name = str(e.get("display_name") or e.get("engine", ""))[:26].ljust(26)
        avail = ("yes" if e.get("available") else "no").ljust(9)
        versions = e.get("versions") or []
        if versions:
            bits = [
                f"{v.get('id')}{'✓' if v.get('available') else '✗'}" for v in versions
            ]
            detail = ", ".join(bits)[:36].ljust(36)
        else:
            detail = str(e.get("detail", ""))[:36].ljust(36)
        print(f"│ {str(i).ljust(2)} │ {name} │ {avail} │ {detail} │")
    print("└────┴────────────────────────────┴───────────┴──────────────────────────────────────┘")


def _resolve_input_path(raw: str) -> Path | None:
    text = raw.strip().strip('"')
    if not text:
        return None
    p = Path(text)
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    else:
        p = p.resolve()
    return p if p.is_file() else None


def _pick_input_file() -> Path | object | None:
    print(f"\nProject root: {ROOT}")
    print("Tip: pick a listed sample or type a path. Esc/b = back.")
    if SAMPLES.is_dir():
        files = sorted(
            p for p in SAMPLES.iterdir() if p.suffix.lower() in {".txt", ".pdf", ".docx"}
        )
        if files:
            print("\nFiles in samples\\:")
            for i, f in enumerate(files, 1):
                print(f"  [{i}] {f.relative_to(ROOT)}")
            print("  Or type a path under the project root / absolute path.")
            choice = prompt_line("Select number or path", default="1")
            if choice is BACK:
                return BACK
            assert isinstance(choice, str)
            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(files):
                    return files[idx - 1]
                print("✗ Invalid number")
                return None
            return _resolve_input_path(choice)

    raw = prompt_line("Input file (.txt/.pdf/.docx)")
    if raw is BACK:
        return BACK
    assert isinstance(raw, str)
    path = _resolve_input_path(raw)
    if path is None:
        print(f"✗ File not found (looked under {ROOT})")
    return path


def _pick_engine(client: httpx.Client) -> tuple[dict, str | None] | object | None:
    r = client.get("/engines")
    r.raise_for_status()
    engines = r.json().get("engines", [])
    if not engines:
        print("✗ No engines reported by API")
        return None

    print("\nAvailable models:")
    for i, e in enumerate(engines, 1):
        mark = "✓" if e.get("available") else "✗"
        print(f"  [{i}] {mark} {e.get('display_name')} ({e.get('engine')})")

    raw = prompt_line(f"Select model [1-{len(engines)}]", default="1")
    if raw is BACK:
        return BACK
    assert isinstance(raw, str)
    if not raw.isdigit() or not (1 <= int(raw) <= len(engines)):
        print("✗ Invalid selection")
        return None
    engine = engines[int(raw) - 1]
    versions = engine.get("versions") or []
    if not versions:
        return engine, None

    print("\nVoices / versions:")
    for i, v in enumerate(versions, 1):
        mark = "✓" if v.get("available") else "✗"
        print(f"  [{i}] {mark} {v.get('id')} — {v.get('detail', '')[:70]}")
    default_idx = next(
        (i for i, v in enumerate(versions, 1) if v.get("available")),
        1,
    )
    vraw = prompt_line(f"Select voice/version", default=str(default_idx))
    if vraw is BACK:
        return BACK
    assert isinstance(vraw, str)
    if not vraw.isdigit() or not (1 <= int(vraw) <= len(versions)):
        print("✗ Invalid version")
        return None
    version_id = versions[int(vraw) - 1].get("id")
    return engine, str(version_id) if version_id else None


def _pick_format() -> str | object:
    print("\nAudio format:")
    print("  [1] wav  (default)")
    print("  [2] mp3")
    choice = prompt_line("Select format", default="1")
    if choice is BACK:
        return BACK
    assert isinstance(choice, str)
    if choice in {"1", "wav"}:
        return "wav"
    if choice in {"2", "mp3"}:
        return "mp3"
    print("✗ format must be wav or mp3")
    return BACK


def _open_audio(path: Path) -> None:
    print(f"Opening in default player: {path}")
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def test_tts(client: httpx.Client) -> None:
    path = _pick_input_file()
    if path is BACK or path is None:
        return
    assert isinstance(path, Path)

    print(f"Using: {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")

    picked = _pick_engine(client)
    if picked is BACK or picked is None:
        return
    engine_info, version = picked
    engine_name = engine_info.get("engine")
    if not engine_name:
        print("✗ Engine missing id")
        return

    audio_format = _pick_format()
    if audio_format is BACK or not isinstance(audio_format, str):
        return

    data: dict[str, str] = {
        "engine": str(engine_name),
        "audio_format": audio_format,
    }
    if version:
        data["version"] = version

    print(
        f"\nSubmitting engine={engine_name} version={version or '-'} format={audio_format}…"
    )
    timeout = 320.0 if str(engine_name) == "google_studio" else 180.0
    with path.open("rb") as f:
        r = client.post(
            "/tts",
            data=data,
            files={"file": (path.name, f, "application/octet-stream")},
            timeout=timeout,
        )
    if r.status_code >= 400:
        print("✗", r.status_code, r.text)
        return

    job_id = r.json().get("job_id")
    print(f"✓ Job queued: {job_id}")
    if not job_id:
        pretty(r.json())
        return

    print("Waiting for result…")
    body = _poll(client, job_id, max_wait=200 if str(engine_name) == "google_studio" else 120)
    if not body:
        return

    if body.get("status") != "completed":
        print("✗ Job failed")
        return

    audio_url = body.get("audio_url")
    if not audio_url:
        print("✗ No audio_url on completed job")
        return

    name = audio_url.rsplit("/", 1)[-1]
    dest = ROOT / "output" / "audio" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        audio = client.get(f"/files/{name}")
        if audio.status_code >= 400:
            print("✗ Could not download audio:", audio.text)
            return
        dest.write_bytes(audio.content)

    # Remove sibling format if both somehow exist
    sibling = dest.with_suffix(".mp3" if dest.suffix.lower() == ".wav" else ".wav")
    if sibling.exists() and sibling != dest:
        try:
            sibling.unlink()
            print(f"  (removed leftover {sibling.name})")
        except OSError:
            pass

    print(f"\n✓ AUDIO: {dest}")
    _open_audio(dest)


def _poll(client: httpx.Client, job_id: str, *, max_wait: int = 120) -> dict | None:
    for _ in range(max_wait):
        r = client.get(f"/jobs/{job_id}")
        r.raise_for_status()
        body = r.json()
        status = body.get("status")
        stage = body.get("stage")
        engine = body.get("engine")
        version = body.get("version")
        print(f"  → status={status} stage={stage} engine={engine} version={version}")
        if status in ("completed", "failed"):
            pretty(body)
            return body
        time.sleep(1.5)
    print("✗ Timeout waiting for job")
    return None


def main() -> int:
    os.chdir(ROOT)
    base = DEFAULT_BASE
    banner()
    if len(sys.argv) > 1:
        base = sys.argv[1].rstrip("/")

    print(f"Working directory: {ROOT}")
    print(f"API base: {base}")
    print("Tip: start the server first with  run_api.cmd")

    while True:
        menu()
        choice = prompt_line("Select", default="")
        if choice is BACK:
            continue
        assert isinstance(choice, str)
        choice = choice.strip()
        try:
            if choice == "4":
                import_lexicon()
            elif choice in {"0", "q", "quit", "exit"}:
                print("Bye.")
                return 0
            elif choice in {"1", "2", "3"}:
                with httpx.Client(base_url=base, timeout=320.0) as client:
                    if choice == "1":
                        health(client)
                    elif choice == "2":
                        list_engines(client)
                    else:
                        test_tts(client)
            elif not choice:
                continue
            else:
                print("Unknown choice — use 1, 2, 3, 4, or 0 (Esc=back)")
        except httpx.ConnectError:
            print(f"\n✗ Cannot connect to {base}. Is the API running? (run_api.cmd)")
        except KeyboardInterrupt:
            print("\n(Interrupted — back to menu)")
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"\n✗ Error: {exc}")
        pause()


if __name__ == "__main__":
    raise SystemExit(main())
