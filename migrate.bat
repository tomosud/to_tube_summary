@echo off
echo === 既存HTMLデータの移行 ===
echo.
echo C:\temp\html 以下の旧フォーマット（モノリシックHTML）を
echo data.js + index.html 形式に変換します。
echo.
echo 旧HTMLは .html.bak にリネームされます（削除はされません）。
echo.
pause

cd /d "%~dp0"
call .venv\Scripts\activate
python ret_youyaku_html.py --migrate "C:\temp\html"

echo.
echo 移行処理が完了しました。
pause
