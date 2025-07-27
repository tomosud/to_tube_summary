@echo off
chcp 65001 > nul
echo === YouTube字幕ダウンローダー（詳細版） ===
echo クリップボードのURLから字幕を取得し、詳細テキストも生成します...

:: 仮想環境のPythonを使用
.\.venv\Scripts\python.exe youtube_transcript_downloader.py --from-bat --detail
