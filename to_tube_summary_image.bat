@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo === YouTube transcript and image summarizer ===
echo Reading a YouTube URL from the clipboard...

set OPENAI_MODEL_STAGE1=gpt-5.4-mini-2026-03-17
set OPENAI_MODEL_STAGE2=gpt-5.4-mini-2026-03-17

:: 代表画像を多めに使い、各章を最大10枚の画像で補足
if not exist ".\.venv\Scripts\python.exe" (
    echo.
    echo [ERROR] Python environment is missing. Run setup.bat first.
    pause
    exit /b 1
)

".\.venv\Scripts\python.exe" "youtube_transcript_downloader.py" --from-bat --vision-mode full
if errorlevel 1 (
    echo.
    echo [ERROR] Processing failed. See the message above.
    pause
    exit /b 1
)
