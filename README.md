# YouTube動画要約ツール

Windowsで動作するYouTube動画の要約ツールです。YouTubeのURLをクリップボードにコピーして実行すると、その動画の内容を要約したHTMLファイルを生成します。
要約にはgeminiを使用します。またYouTubeのstoryboardからサムネイルを作成します。

![image](https://github.com/user-attachments/assets/51177fbd-f2d7-4e65-a5b6-998de72b5376)


## 必要なもの

- Windows 10/11
- Python 3.8以上
- Google Cloud Platformで取得したGemini API Key
  - [Google AI Studio](https://aistudio.google.com/app/apikey)からAPIキーを取得できます
  - 初回実行時にダイアログで入力を求められます

## セットアップ

1. このリポジトリをクローンまたはダウンロード

2. `setup.bat`を実行して初期設定を行う
   -Pythonの仮想環境を作成し、依存パッケージがインストールされます


## 使い方

1. YouTubeの動画ページでURLをコピー（クリップボードに保存）

2. `to_tube_summary.bat`を実行
   - 自動的に字幕をダウンロードし、内容を要約したHTMLファイルを生成
   - 生成されたHTMLファイルには動画の各部分へのリンクが含まれており、クリックすると該当シーンにジャンプできます

   - ※初回実行時のみ
   - 初回実行時にGemini APIキーの入力を求められます
   - 入力されたAPIキーは`api_key.txt`に保存され、次回以降は自動的に読み込まれます
   - APIキーを変更したい場合は`api_key.txt`を削除すると、次回起動時に再度入力を求められます
## 注意事項

- 英語/日本語の字幕のみ対応しています
- 字幕が無い動画では動作しません
- 処理時間は動画の長さによって変動します（数分程度）
- APIキーは外部に公開しないようご注意ください（`.gitignore`に`api_key.txt`は設定済み）
