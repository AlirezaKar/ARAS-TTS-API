# Asterisk / Issabel — Google Studio TTS (Apps Script)

The PBX and TTS-API both call the same **Apps Script** `/exec` URL.
The AI Studio key lives **only inside** [`Code.gs`](Code.gs) — not on the Asterisk host and not as `GEMINI_API_KEY` in TTS-API.

```text
Phone / toolbox → google_studio engine
               → GOOGLE_APPS_SCRIPT_URL (/exec)
               → Code.gs → Gemini TTS
               → base64 audio → WAV
```

---

## What you need (only these files)

| File | Where |
|------|--------|
| [`Code.gs`](Code.gs) | Paste into Google Apps Script |
| [`gemini_tts.py`](gemini_tts.py) | Asterisk host (`/usr/local/bin/`) |
| [`dialplan-snippet.conf`](dialplan-snippet.conf) | FreePBX/Issabel custom dialplan |
| [`install_on_asterisk.sh`](install_on_asterisk.sh) | Optional PBX installer |

---

## Step 1 — Apps Script

1. [script.google.com](https://script.google.com) → New project  
2. Paste [`Code.gs`](Code.gs) → set `GEMINI_API_KEY` inside the script  
3. **Deploy → Web app → Execute as: Me → Who has access: Anyone**  
4. Copy the **`/exec`** URL into TTS-API `.env` as `GOOGLE_APPS_SCRIPT_URL`

Test:

```bash
curl -L -X POST "YOUR_/exec_URL" -H "Content-Type: application/json" -d "{\"text\":\"سلام\"}"
```

Expect long base64, not HTML.

---

## Step 2 — TTS-API

```env
GOOGLE_APPS_SCRIPT_URL=https://script.google.com/macros/s/XXXX/exec
```

Restart API → toolbox **3) Test TTS** → pick `google_studio`.

---

## Step 3 — Asterisk (optional)

```bash
sudo GOOGLE_APPS_SCRIPT_URL='https://script.google.com/macros/s/XXXX/exec' \
  bash deploy/asterisk/install_on_asterisk.sh
```

Add dialplan from [`dialplan-snippet.conf`](dialplan-snippet.conf), then `asterisk -rx "dialplan reload"`.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| HTML / `ppConfig` | Redeploy: **Anyone** + `/exec` URL |
| `ERROR: set GEMINI_API_KEY in Code.gs` | Put key in Code.gs and create a **new** deployment |
| `GOOGLE_APPS_SCRIPT_URL not set` | Add URL to `.env` and restart API |
