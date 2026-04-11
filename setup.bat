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

echo APIキーの暗号化移行を確認中...
if exist api_key.txt (
    echo api_key.txt を検出しました。暗号化して api_key.bin に移行します...
    python -c "import win32crypt, os; key=open('api_key.txt','r').read().strip(); enc=win32crypt.CryptProtectData(key.encode('utf-8'),None,None,None,None,0); open('localsettings.bin','wb').write(enc); os.remove('api_key.txt'); print('移行完了：api_key.txt を削除し localsettings.bin に暗号化しました')"
)

echo セットアップが完了しました！
pause
