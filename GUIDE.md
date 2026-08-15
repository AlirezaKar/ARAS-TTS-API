# Persian TTS-API — Postman Guide

How to call the live API from [Postman](https://www.postman.com/) on your laptop.

**Base URL**

```text
http://45.95.88.79:5004
```

> Tip: In Postman, create an environment variable `base_url` = `http://45.95.88.79:5004` and use `{{base_url}}/...` in requests.

---

## **Flow overview*

```text
1. GET  /health          → is the server up?
2. GET  /engines         → which models are available?
3. POST /tts             → upload text → get job_id  (status 202)
4. GET  /jobs/{job_id}   → poll until completed / failed
5. GET  /files/{name}    → download the audio
```

TTS is **async**: the first `POST /tts` only queues the job. Audio comes after polling.

---

## 1. **Health check*


|            |                       |
| ---------- | --------------------- |
| **Method** | `GET`                 |
| **URL**    | `{{base_url}}/health` |
| **Body**   | none                  |


**Example response**

```json
{
  "status": "ok",
  "app": "Persian TTS-API",
  "version": "1.0.0"
}
```

---

## 2. List engines (optional)


|            |                        |
| ---------- | ---------------------- |
| **Method** | `GET`                  |
| **URL**    | `{{base_url}}/engines` |


Useful to see which engines are ready and which Gemini voices (`version`) you can pick.

---

## 3. **Create a TTS job*


|            |                                                         |
| ---------- | ------------------------------------------------------- |
| **Method** | `POST`                                                  |
| **URL**    | `{{base_url}}/tts`                                      |
| **Params** | leave **empty** (do not put fields in the query string) |
| **Body**   | **form-data**                                           |


### **Form fields*


| Key             | Type in Postman | Required | Example                     | Notes                                                        |
| --------------- | --------------- | -------- | --------------------------- | ------------------------------------------------------------ |
| `file`          | **File**        | yes      | select `hello.txt`          | `.txt` / `.pdf` / `.docx` only. Use type **File**, not Text. |
| `engine`        | Text            | yes      | `gemini` or `google_studio` |                                                              |
| `version`       | Text            | no       | `Kore`                      | Gemini **voice** only. Omit for `google_studio`.             |
| `audio_format`  | Text            | no       | `wav` or `mp3`              | Default is `wav`.                                            |
| `special_words` | Text            | no       | `{"foo":"بار"}`             | Optional JSON object.                                        |


### How to set `file` correctly

1. Open **Body** → **form-data**
2. For the `file` row, change the type dropdown from **Text** → **File**
3. Click **Select Files** and pick a file from your laptop
  Postman **uploads** the bytes — you do **not** send a server path or directory.

### Example (Gemini)


| Key            | Type | Value         |
| -------------- | ---- | ------------- |
| `file`         | File | *(your file)* |
| `engine`       | Text | `gemini`      |
| `version`      | Text | `Kore`        |
| `audio_format` | Text | `wav`         |


### Example (Google Studio)


| Key            | Type | Value           |
| -------------- | ---- | --------------- |
| `file`         | File | *(your file)*   |
| `engine`       | Text | `google_studio` |
| `audio_format` | Text | `mp3`           |


### Success response — `202 Accepted`

```json
{
  "job_id": "7e125bfa-307b-4cff-98f9-529c604e21c8",
  "status": "queued"
}
```

Copy `job_id` for the next step.

---

## 4. Poll job status


|            |                              |
| ---------- | ---------------------------- |
| **Method** | `GET`                        |
| **URL**    | `{{base_url}}/jobs/<job_id>` |


Replace `<job_id>` with the value from step 3. Send every few seconds until finished.


| `status`             | Meaning                                    |
| -------------------- | ------------------------------------------ |
| `queued` / `running` | Still working — wait and poll again        |
| `completed`          | Success — look for `audio_url`             |
| `failed`             | Error — check the error fields in the JSON |


Jobs (especially `google_studio`) can take from under a minute to several minutes.

**When completed**, the body includes something like:

```json
{
  "job_id": "...",
  "status": "completed",
  "audio_url": "/files/some-name.wav"
}
```

---

## 5. **Download the audio*


|            |                                 |
| ---------- | ------------------------------- |
| **Method** | `GET`                           |
| **URL**    | `{{base_url}}/files/<filename>` |


Use the filename from `audio_url` (the part after `/files/`).

In Postman: **Send and Download** to save the file locally.

---

## Common mistakes


| Mistake                              | What happens                         | Fix                                      |
| ------------------------------------ | ------------------------------------ | ---------------------------------------- |
| Fields in **Params** (`?engine=...`) | `422` — “Field required” in **body** | Put fields in **Body → form-data** only  |
| `file` type = Text (`hello.txt`)     | Upload empty / wrong                 | Set type to **File** and select the file |
| Key named `File`                     | May not bind                         | Use lowercase `file`                     |
| Expecting audio from `POST /tts`     | Only get `job_id`                    | Poll `/jobs/{id}`, then `/files/...`     |
| `version` with `google_studio`       | `400`                                | Omit `version` for Studio                |


---

## Quick PowerShell checks (optional)

```powershell
Invoke-RestMethod http://45.95.88.79:5004/health
Invoke-RestMethod http://45.95.88.79:5004/engines
```

File upload is easier in Postman than in PowerShell.