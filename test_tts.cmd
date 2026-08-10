@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\smoke_tts.py %*
) else (
  python scripts\smoke_tts.py %*
)
