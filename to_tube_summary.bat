@echo off
chcp 65001 > nul
echo === YouTube字幕ダウンローダー ===
echo クリップボードのURLから字幕を取得します...

:: モデル名を環境変数で設定
set OPENAI_MODEL_STAGE1=gpt-5.4-mini-2026-03-17
set OPENAI_MODEL_STAGE2=gpt-5.4-mini-2026-03-17

:: 仮想環境のPythonを使用
.\.venv\Scripts\python.exe youtube_transcript_downloader.py --from-bat

