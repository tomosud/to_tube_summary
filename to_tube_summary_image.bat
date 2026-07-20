@echo off
chcp 65001 > nul
echo === YouTube字幕＋画像 要約ツール ===
echo クリップボードのURLから字幕と画像を取得します...

set OPENAI_MODEL_STAGE1=gpt-5.4-mini-2026-03-17
set OPENAI_MODEL_STAGE2=gpt-5.4-mini-2026-03-17

:: 代表画像を多めに使い、各章を最大10枚の画像で補足
.\.venv\Scripts\python.exe youtube_transcript_downloader.py --from-bat --vision-mode full
