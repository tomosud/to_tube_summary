@echo off
echo 仮想環境をセットアップします...

rem 既存の仮想環境が存在する場合は削除
if exist .venv (
    echo 既存の仮想環境を削除中...
    rmdir /s /q .venv
)

echo 新しい仮想環境を作成中...
python -m venv .venv

echo 仮想環境をアクティベート中...
call .venv\Scripts\activate

echo パッケージをインストール中...
python -m pip install -r requirements.txt

echo セットアップが完了しました！
pause
