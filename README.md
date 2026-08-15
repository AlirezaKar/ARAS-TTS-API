# Persian TTS-API

Standalone **Persian Text-to-Speech API** built with FastAPI. Accepts `.txt` / `.pdf` / `.docx`, applies harakat fine-tuning, synthesizes with **Gemini (direct API)** or **Google Studio (Apps Script)**.

Default listen port: **5004**.

## Requirements

- **Python 3.11 or 3.12 recommended**
- `imageio-ffmpeg` / `pydub` for format conversion
- **Gemini direct:** `GEMINI_API_KEY` from [Google AI Studio](https://aistudio.google.com/apikey)
- **Google Studio:** `GOOGLE_APPS_SCRIPT_URL` (`/exec`); key lives inside [`deploy/asterisk/Code.gs`](deploy/asterisk/Code.gs)

## Quick start

```bat
setup_all.cmd
copy .env.sample .env
REM edit .env — set GEMINI_API_KEY and/or GOOGLE_APPS_SCRIPT_URL
run_api.cmd
toolbox.cmd
```

## Engines

| Engine | Display name | Notes |
|--------|--------------|--------|
| `gemini` | Gemini TTS (direct API) | `GEMINI_API_KEY`; `version` = voice (`Kore`, `Puck`, …). Default backend `developer` (AI Studio). Optional `GEMINI_TTS_BACKEND=cloud` for [Cloud Gemini-TTS](https://docs.cloud.google.com/text-to-speech/docs/gemini-tts). |
| `google_studio` | Google Studio (Apps Script) | `GOOGLE_APPS_SCRIPT_URL` only; voice/model in Code.gs |

### Toolbox

- **3) Test TTS** — pick file → model (`gemini` / `google_studio`) → voice (numbered) → format (wav default)  
- Esc (or `b`) goes back / cancels a prompt  

## Env

```env
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash-preview-tts
GEMINI_VOICE=Kore
GEMINI_TTS_BACKEND=developer
GOOGLE_APPS_SCRIPT_URL=
```

- `developer` — direct `generativelanguage.googleapis.com` with API key (same family as Flash TTS; free-tier friendly)  
- `cloud` — `texttospeech.googleapis.com/v1/text:synthesize` per Cloud docs (often needs GCP project / billing)

## Google Studio / Asterisk

Unchanged. See [`deploy/asterisk/README.md`](deploy/asterisk/README.md).

## Fine-tuning

`fine_tuning/lexicon.json` + toolbox **4)** import to SQLite — unchanged.

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness |
| GET | `/engines` | Engines + availability |
| POST | `/tts` | Enqueue job |
| GET | `/jobs/{id}` | Poll (+ `meta.timing_ms`) |
| GET | `/files/{name}` | Download audio |
| POST | `/fine-tune/preview` | Preview lexicon |
| POST | `/feedback` | Queue correction |
