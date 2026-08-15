# Persian TTS-API

Standalone **Persian Text-to-Speech API** built with FastAPI. Accepts `.txt` / `.pdf` / `.docx`, applies harakat (short-vowel) fine-tuning, synthesizes audio at selectable accuracy tiers, delivers to **Bale / Telegram / WhatsApp**, and returns async job status for the target system.

## Requirements

- **Python 3.11 or 3.12 recommended** (many TTS wheels do not support 3.14 yet)
- FFmpeg on PATH if you need reliable MP3 conversion via `pydub`
- Optional: Piper Persian `.onnx` voices under `models/`
- Optional: Bot tokens / Playwright login sessions for messaging

## Quick start

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.sample .env
```

Messaging automation uses your installed **Microsoft Edge** (`PLAYWRIGHT_CHANNEL=msedge`). No `playwright install chromium` needed.

Place Persian Piper models (optional but recommended):

- `models/fa_IR-amir-medium.onnx` (+ `.onnx.json`)
- `models/fa_IR-mana-medium.onnx` (+ `.onnx.json`) for balanced / LCA path

Start API:

```bat
run_api.cmd
```

Or:

```bat
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open docs: http://127.0.0.1:8000/docs

CLI toolbox:

```bat
toolbox.cmd
```

## API overview

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness |
| GET | `/engines` | Accuracy tiers + availability |
| POST | `/tts` | Enqueue TTS + messaging job (`202` + `job_id`) |
| GET | `/jobs/{job_id}` | Poll status, `audio_url`, `send` feedback |
| GET | `/files/{name}` | Download generated audio |
| POST | `/fine-tune/preview` | Preview harakat lexicon application |
| POST | `/feedback` | Queue pronunciation correction (pending only) |
| POST | `/messaging/test` | Test platform send only |
| POST | `/phone-map` | Map phone → bot `chat_id` |

### `POST /tts` (multipart)

- `file` — `.txt` / `.pdf` / `.docx`
- `special_words` — JSON string map, e.g. `{"کلمه":"کَلِمَه"}` (Unicode harakat)
- `phone_number` — destination phone
- `platform` — `bale` \| `telegram` \| `whatsapp`
- `accuracy` — `fast` \| `balanced` \| `high` \| `premium`
- `audio_format` — `mp3` \| `wav`
- `elevenlabs_model` — (optional, for `premium`) `v1` \| `v2` \| `v3`

| Version | ElevenLabs model | Notes |
|---------|------------------|--------|
| `v1` | `eleven_flash_v2_5` | Fastest / lowest latency |
| `v2` | `eleven_multilingual_v2` | High quality (default) |
| `v3` | `eleven_v3` | Most advanced / expressive |

Default comes from `ELEVENLABS_MODEL_ID` in `.env` (alias or full model id).

Poll until `status` is `completed` or `failed`. On success:

- `audio_url` — for the target system to store
- `send.success` / `send.detail` — social-media delivery feedback

## Accuracy → engines

| Accuracy | Preferred engine |
|----------|------------------|
| `fast` | `persian-tts-mrj` (falls back to Piper / edge-tts / stub) |
| `balanced` | Piper + Mana/LCA model |
| `high` | TTSKit multi-engine |
| `premium` | ElevenLabs |

If the preferred engine is missing, the registry walks fallbacks so the API still works for development (including an offline stub beep).

## Fine-tuning (harakat)

Live lexicon: SQLite at `fine_tuning/pronunciation.db` (POS-aware via hazm when installed).  
Seed JSON (import only): [`fine_tuning/lexicon.json`](fine_tuning/lexicon.json)

```bat
python scripts/import_lexicon_json.py
pip install hazm
```

(`hazm` is optional; without it, lookups still work using null context tags.)
Supported marks:

- U+064E fatha `َ`
- U+0650 kasra `ِ`
- U+064F damma `ُ`
- U+0652 sukun `ْ`

Request `special_words` overrides the lexicon.  
Report bad pronunciations with `POST /feedback` (queues `pending_corrections`; does **not** auto-write the live lexicon).

## Messaging (hybrid, Iran-ready)

| Platform | Primary | Fallback |
|----------|---------|----------|
| Bale | Bot API (`tapi.bale.ai`) | Playwright `web.bale.ai` |
| Telegram | Bot API | Playwright Telegram Web |
| WhatsApp | Playwright WhatsApp Web | Optional Cloud API |

Bot APIs need a **phone → chat_id** map in [`fine_tuning/phone_chat_map.json`](fine_tuning/phone_chat_map.json) (or `POST /phone-map`). Users typically `/start` the bot once so you can store their `chat_id`.

## Project layout

```
app/                 FastAPI app, services, TTS & messaging
cli/toolbox.py       Interactive CMD toolbox
fine_tuning/         lexicon + phone map
models/              Piper onnx voices
output/              uploads, jobs, audio, sessions
```

## Testing (hear the audio)

1. Set `SKIP_MESSAGING=true` in `.env` (already set for local tests).
2. Start API: `run_api.cmd`
3. In another terminal: `test_tts.cmd`

That submits [`samples/hello.txt`](samples/hello.txt), polls the job, then opens the WAV in your default Windows player.

Or use the toolbox:

```bat
toolbox.cmd
```

Menu:

1. Health check  
2. List engines / models  
3. Test TTS — pick a file under the project root (lists `samples\` first), then auto-polls and can open the audio  
4. Import `lexicon.json` into the SQLite pronunciation DB (same as `python scripts\import_lexicon_json.py`)

Audio files are also saved under `output\audio\`.

Swagger UI: http://127.0.0.1:8000/docs

## Playwright on Iran networks

`playwright install chromium` often fails here (CDN geo-block / 403). **You do not need it.**

This project defaults to installed **Microsoft Edge**:

```env
PLAYWRIGHT_CHANNEL=msedge
```

Set `chrome` only if you prefer Google Chrome. Only set `chromium` if you somehow obtained Playwright’s bundled browser.

Bot messaging (Bale/Telegram tokens + `phone_chat_map.json`) does not need Playwright at all.