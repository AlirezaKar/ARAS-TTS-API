"""
Interactive CLI toolbox for Persian TTS-API.

Usage:
  python -m cli.toolbox
  toolbox.cmd
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

DEFAULT_BASE = "http://127.0.0.1:8000"


def banner() -> None:
    print(
        r"""
╔══════════════════════════════════════════╗
║       Persian TTS-API Toolbox            ║
║       FastAPI · Harakat · Messaging      ║
╚══════════════════════════════════════════╝
"""
    )


def menu() -> None:
    print(
        """
  1) Health check
  2) List engines
  3) Submit TTS job
  4) Poll job status
  5) Download audio
  6) Fine-tune preview
  7) Test messaging only
  8) Register phone → chat_id map
  9) Set API base URL
  0) Exit
"""
    )


def pause() -> None:
    input("\nPress Enter to continue...")


def pretty(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def health(client: httpx.Client) -> None:
    r = client.get("/health")
    r.raise_for_status()
    print("\n✓ Health")
    pretty(r.json())


def list_engines(client: httpx.Client) -> None:
    r = client.get("/engines")
    r.raise_for_status()
    engines = r.json().get("engines", [])
    print("\n┌────────────┬──────────────────┬───────────┬────────────────────────────┐")
    print("│ Accuracy   │ Engine           │ Available │ Detail                     │")
    print("├────────────┼──────────────────┼───────────┼────────────────────────────┤")
    for e in engines:
        acc = str(e.get("accuracy", ""))[:10].ljust(10)
        eng = str(e.get("engine", ""))[:16].ljust(16)
        avail = ("yes" if e.get("available") else "no").ljust(9)
        detail = str(e.get("detail", ""))[:26].ljust(26)
        print(f"│ {acc} │ {eng} │ {avail} │ {detail} │")
    print("└────────────┴──────────────────┴───────────┴────────────────────────────┘")


def submit_job(client: httpx.Client) -> None:
    path = input("Input file path (.txt/.pdf/.docx): ").strip().strip('"')
    p = Path(path)
    if not p.exists():
        print("✗ File not found")
        return
    phone = input("Phone number: ").strip()
    platform = input("Platform [bale|telegram|whatsapp]: ").strip() or "bale"
    accuracy = input("Accuracy [fast|balanced|high|premium] (balanced): ").strip() or "balanced"
    audio_format = input("Audio format [mp3|wav] (mp3): ").strip() or "mp3"
    special = input('Special words JSON (optional, e.g. {"کلمه":"کَلِمَه"}): ').strip()

    data = {
        "phone_number": phone,
        "platform": platform,
        "accuracy": accuracy,
        "audio_format": audio_format,
    }
    if accuracy == "premium":
        el_model = input(
            "ElevenLabs model [v1=flash | v2=multilingual | v3=eleven_v3] (v2): "
        ).strip() or "v2"
        data["elevenlabs_model"] = el_model
    if special:
        data["special_words"] = special

    files = {"file": (p.name, p.open("rb"), "application/octet-stream")}
    r = client.post("/tts", data=data, files=files)
    if r.status_code >= 400:
        print("✗", r.status_code, r.text)
        return
    print("\n✓ Job queued")
    pretty(r.json())
    job_id = r.json().get("job_id")
    if job_id and input("Poll until done? [Y/n]: ").strip().lower() != "n":
        _poll(client, job_id)


def _poll(client: httpx.Client, job_id: str) -> None:
    while True:
        r = client.get(f"/jobs/{job_id}")
        r.raise_for_status()
        body = r.json()
        status = body.get("status")
        stage = body.get("stage")
        print(f"  → status={status} stage={stage}")
        if status in ("completed", "failed"):
            pretty(body)
            return
        time.sleep(1.5)


def poll_job(client: httpx.Client) -> None:
    job_id = input("Job ID: ").strip()
    auto = input("Auto-poll until done? [Y/n]: ").strip().lower() != "n"
    if auto:
        _poll(client, job_id)
    else:
        r = client.get(f"/jobs/{job_id}")
        if r.status_code >= 400:
            print("✗", r.status_code, r.text)
            return
        pretty(r.json())


def download_audio(client: httpx.Client) -> None:
    job_id = input("Job ID (or leave empty to use audio URL name): ").strip()
    if job_id:
        r = client.get(f"/jobs/{job_id}")
        r.raise_for_status()
        url = r.json().get("audio_url")
        if not url:
            print("✗ No audio_url on job yet")
            return
        name = url.rsplit("/", 1)[-1]
    else:
        name = input("File name under /files/: ").strip()
    dest = input(f"Save as [{name}]: ").strip() or name
    r = client.get(f"/files/{name}")
    if r.status_code >= 400:
        print("✗", r.status_code, r.text)
        return
    Path(dest).write_bytes(r.content)
    print(f"✓ Saved {dest} ({len(r.content)} bytes)")


def fine_tune_preview(client: httpx.Client) -> None:
    text = input("Persian text: ").strip()
    special_raw = input("Special words JSON (optional): ").strip() or "{}"
    try:
        special = json.loads(special_raw)
    except json.JSONDecodeError as exc:
        print("✗ Invalid JSON:", exc)
        return
    r = client.post("/fine-tune/preview", json={"text": text, "special_words": special})
    r.raise_for_status()
    print("\n✓ Preview")
    pretty(r.json())


def test_messaging(client: httpx.Client) -> None:
    phone = input("Phone number: ").strip()
    platform = input("Platform [bale|telegram|whatsapp]: ").strip() or "bale"
    text = input("Caption [تست ارسال]: ").strip() or "تست ارسال از Persian TTS-API"
    audio = input("Audio path (optional): ").strip() or None
    payload = {
        "phone_number": phone,
        "platform": platform,
        "text": text,
        "audio_path": audio,
    }
    r = client.post("/messaging/test", json=payload)
    print(r.status_code)
    pretty(r.json())


def register_phone_map(client: httpx.Client) -> None:
    phone = input("Phone number: ").strip()
    platform = input("Platform [bale|telegram|whatsapp]: ").strip() or "bale"
    chat_id = input("chat_id: ").strip()
    r = client.post(
        "/phone-map",
        data={"phone_number": phone, "platform": platform, "chat_id": chat_id},
    )
    print(r.status_code)
    pretty(r.json())


def main() -> int:
    base = DEFAULT_BASE
    banner()
    if len(sys.argv) > 1:
        base = sys.argv[1].rstrip("/")

    print(f"API base: {base}")
    print("Tip: start the server with  python -m app.main")

    while True:
        menu()
        choice = input("Select> ").strip()
        try:
            with httpx.Client(base_url=base, timeout=120.0) as client:
                if choice == "1":
                    health(client)
                elif choice == "2":
                    list_engines(client)
                elif choice == "3":
                    submit_job(client)
                elif choice == "4":
                    poll_job(client)
                elif choice == "5":
                    download_audio(client)
                elif choice == "6":
                    fine_tune_preview(client)
                elif choice == "7":
                    test_messaging(client)
                elif choice == "8":
                    register_phone_map(client)
                elif choice == "9":
                    base = input(f"New base URL [{base}]: ").strip().rstrip("/") or base
                    print(f"API base: {base}")
                    continue
                elif choice == "0":
                    print("Bye.")
                    return 0
                else:
                    print("Unknown choice")
        except httpx.ConnectError:
            print(f"\n✗ Cannot connect to {base}. Is the API running?")
        except Exception as exc:  # noqa: BLE001
            print(f"\n✗ Error: {exc}")
        pause()


if __name__ == "__main__":
    raise SystemExit(main())
