@echo off
chcp 65001 > nul
echo === YouTube字幕ダウンローダー（安価版） ===
echo クリップボードのURLから字幕を取得します...

:: モデル名を環境変数で設定（安価なminiモデル）
set OPENAI_MODEL=gpt-5-mini-2025-08-07

:: 仮想環境のPythonを使用
.\.venv\Scripts\python.exe youtube_transcript_downloader.py --from-bat
