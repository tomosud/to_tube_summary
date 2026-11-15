@echo off
chcp 65001 > nul
echo === YouTube字幕ダウンローダー（安価版） ===
echo クリップボードのURLから字幕を取得します...

:: モデル名を環境変数で設定
set ANTHROPIC_MODEL_STAGE1=claude-haiku-5-5
set ANTHROPIC_MODEL_STAGE2=claude-haiku-5-5

:: 仮想環境のPythonを使用
.\.venv\Scripts\python.exe youtube_transcript_downloader.py --from-bat
