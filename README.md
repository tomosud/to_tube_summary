# YouTube動画要約ツール

Windowsで動作するYouTube動画の要約ツールです。YouTubeのURLをクリップボードにコピーして実行すると、その動画の内容を要約したHTMLファイルを生成します。

要約にはOpenAI APIを使用します。

またYouTubeのstoryboardからサムネイルを作成します。

![image](https://github.com/user-attachments/assets/51177fbd-f2d7-4e65-a5b6-998de72b5376)


## 必要なもの

- Windows 10/11
- Python 3.8以上
- OpenAIのAPIキー

OpenAIのAPIキーには、学習利用を条件にした無料枠がありプロジェクトを指定できるので、専用のプロジェクトを作りAPIKeyを発行すると良いかも。

参考
https://qiita.com/youtoy/items/2930eaa43082555b5d5f

  - 初回実行時にダイアログで入力を求められます

## セットアップ

1. このリポジトリをクローンまたはダウンロード

2. `setup.bat`を実行して初期設定を行う
   - Pythonの仮想環境を作成し、依存パッケージがインストールされます


## 使い方

### 基本版（高性能モデル）
1. YouTubeの動画ページでURLをコピー（クリップボードに保存）
2. `to_tube_summary.bat`を実行
   - 自動的に字幕をダウンロードし、内容を要約したHTMLファイルを生成
   - 生成されたHTMLファイルには動画の各部分へのリンクが含まれており、クリックすると該当シーンにジャンプできます

### 詳細版（高性能モデル）
- `to_tube_summary_detail.bat`を実行
- 通常の要約に加えて、字幕全文を整形した詳細テキストも生成されます

### 安価版（軽量モデル）
- `to_tube_summary_cheep.bat`を実行
- GPT-5-miniを使用するため、コストを抑えられます
- 品質は基本版より劣る場合があります


## バッチファイル一覧

| ファイル名 | モデル | 説明 |
|-----------|--------|------|
| `to_tube_summary.bat` | gpt-5.2-2025-12-11 | 標準版（高品質） |
| `to_tube_summary_detail.bat` | gpt-5.2-2025-12-11 | 詳細版（要約＋全文整形） |
| `to_tube_summary_cheep.bat` | gpt-5-mini-2025-08-07 | 安価版（軽量モデル） |


## 別のモデルを使うバッチファイルを追加する方法

1. 既存のbatファイル（例: `to_tube_summary.bat`）をコピー
2. `set OPENAI_MODEL=` の行で使用したいモデル名を指定

例: GPT-4oを使用する場合
```batch
@echo off
chcp 65001 > nul
echo === YouTube字幕ダウンローダー（GPT-4o版） ===
echo クリップボードのURLから字幕を取得します...

:: モデル名を環境変数で設定
set OPENAI_MODEL=gpt-4o

:: 仮想環境のPythonを使用
.\.venv\Scripts\python.exe youtube_transcript_downloader.py --from-bat
```

### 詳細モード対応版の場合
末尾に `--detail` フラグを追加:
```batch
.\.venv\Scripts\python.exe youtube_transcript_downloader.py --from-bat --detail
```


## 初回実行時の設定

- 初回実行時にOpenAI APIキーの入力を求められます
- 入力されたAPIキーは`api_key.txt`に保存され、次回以降は自動的に読み込まれます
- APIキーを変更したい場合は`api_key.txt`を削除すると、次回起動時に再度入力を求められます


## 出力ファイル

生成されるファイルは `C:\temp\html\[動画タイトル]\` に保存されます：

- `[動画タイトル].html` - 要約HTML
- `[動画タイトル].html.txt` - 要約のMarkdownテキスト
- `info.json` - 動画のメタ情報（タイトル、投稿者、説明文など）
- `Thumbnail.jpg` - サムネイル画像
- `images/` - ストーリーボードからスライスした画像


## 技術仕様

### 依存関係
- **youtube-transcript-api**: 字幕取得
- **yt-dlp**: ストーリーボード・サムネイル取得
- **openai**: OpenAI API クライアント
- **Pillow**: 画像処理
- **pyperclip**: クリップボード操作
- **Python**: 3.8以上

### モデル設定
- 環境変数 `OPENAI_MODEL` でモデルを切り替え可能
- デフォルト: `gpt-5.2-2025-12-11`


## 注意事項

- 英語/日本語の字幕のみ対応しています
- 字幕が無い動画では動作しません
- 処理時間は動画の長さによって変動します
- APIキーは外部に公開しないようご注意ください（`.gitignore`に`api_key.txt`は設定済み）
