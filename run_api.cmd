@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set PY=.venv\Scripts\python.exe
) else (
  set PY=python
)

echo Starting Persian TTS-API on http://127.0.0.1:5004 ...
"%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 5004 --reload
endlocal
