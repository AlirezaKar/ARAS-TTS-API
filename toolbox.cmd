@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set PY=.venv\Scripts\python.exe
) else (
  set PY=python
)

echo.
echo Starting Persian TTS-API Toolbox...
echo.
"%PY%" -m cli.toolbox %*
endlocal
