@echo off
chcp 65001 > nul
echo === YouTube字幕ダウンローダー（詳細版） ===
echo クリップボードのURLから字幕を取得し、詳細テキストも生成します...

:: モデル名を環境変数で設定
set OPENAI_MODEL=gpt-5.2-2025-12-11

:: 仮想環境のPythonを使用
.\.venv\Scripts\python.exe youtube_transcript_downloader.py --from-bat --detail
