/**
 * Persian / Gemini TTS Web App for Asterisk + TTS-API.
 *
 * Setup:
 * 1. script.google.com → New project → paste this into Code.gs
 * 2. Set GEMINI_API_KEY below (from https://aistudio.google.com/apikey)
 * 3. Deploy → New deployment → Type: Web app
 *      Execute as: Me
 *      Who has access: Anyone
 * 4. Copy the /exec URL into:
 *      - Asterisk:  export GOOGLE_APPS_SCRIPT_URL='...'
 *      - TTS-API:   GOOGLE_APPS_SCRIPT_URL=... in .env (optional if GEMINI_API_KEY is set)
 *
 * Contract:
 *   POST JSON  { "text": "سلام" }
 *   or form    text=سلام
 *   Response:  plain base64 (PCM s16le 24kHz from Gemini TTS, or WAV if already RIFF)
 */

var GEMINI_API_KEY = "PASTE_YOUR_AI_STUDIO_KEY_HERE";
var GEMINI_MODEL = "gemini-2.5-flash-preview-tts";
var GEMINI_VOICE = "Kore";

function doGet(e) {
  return ContentService.createTextOutput(
    JSON.stringify({
      ok: true,
      usage: 'POST {"text":"..."} for TTS',
      model: GEMINI_MODEL,
      voice: GEMINI_VOICE,
    })
  ).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    var text = _extractText(e);
    if (!text) {
      return _plain("ERROR: missing text");
    }
    if (!GEMINI_API_KEY || GEMINI_API_KEY.indexOf("PASTE_") === 0) {
      return _plain("ERROR: set GEMINI_API_KEY in Code.gs");
    }

    var b64 = _geminiTtsBase64(text);
    return _plain(b64);
  } catch (err) {
    return _plain("ERROR: " + (err && err.message ? err.message : String(err)));
  }
}

function _extractText(e) {
  if (e && e.parameter && e.parameter.text) {
    return String(e.parameter.text).trim();
  }
  if (e && e.postData && e.postData.contents) {
    var raw = e.postData.contents;
    try {
      var body = JSON.parse(raw);
      if (body && body.text) {
        return String(body.text).trim();
      }
    } catch (ignore) {
      // not JSON
    }
    // plain body as text
    if (raw && raw.trim() && raw.trim().charAt(0) !== "{") {
      return raw.trim();
    }
  }
  return "";
}

function _geminiTtsBase64(text) {
  var url =
    "https://generativelanguage.googleapis.com/v1beta/models/" +
    GEMINI_MODEL +
    ":generateContent?key=" +
    encodeURIComponent(GEMINI_API_KEY);

  var payload = {
    contents: [{ parts: [{ text: text }] }],
    generationConfig: {
      responseModalities: ["AUDIO"],
      speechConfig: {
        voiceConfig: {
          prebuiltVoiceConfig: { voiceName: GEMINI_VOICE },
        },
      },
    },
  };

  var resp = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  });

  var code = resp.getResponseCode();
  var body = resp.getContentText();
  if (code < 200 || code >= 300) {
    throw new Error("Gemini HTTP " + code + ": " + body.substring(0, 400));
  }

  var json = JSON.parse(body);
  if (json.error) {
    throw new Error(JSON.stringify(json.error));
  }

  var part =
    json.candidates &&
    json.candidates[0] &&
    json.candidates[0].content &&
    json.candidates[0].content.parts &&
    json.candidates[0].content.parts[0];

  var inline = part && (part.inlineData || part.inline_data);
  if (!inline || !inline.data) {
    throw new Error("No audio in Gemini response: " + body.substring(0, 400));
  }
  return inline.data; // base64 PCM (or container) — Asterisk helper wraps PCM as WAV
}

function _plain(text) {
  return ContentService.createTextOutput(text).setMimeType(
    ContentService.MimeType.TEXT
  );
}
