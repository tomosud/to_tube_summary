@echo off
chcp 65001 > nul
echo === YouTube字幕ダウンローダー ===
echo クリップボードのURLから字幕を取得します...

:: 仮想環境のPythonを使用
.\.venv\Scripts\python.exe youtube_transcript_downloader.py --from-bat

pause