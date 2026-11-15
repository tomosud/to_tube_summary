@echo off
chcp 65001 > nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" serve_pages.py --open ""
) else (
  python serve_pages.py --open ""
)
