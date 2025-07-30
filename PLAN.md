# 詳細版実装計画

## 2025年7月30日時点のステータス

### ✅ 完了した実装
- **youtube-transcript-api 1.2.1対応**: 古いAPI仕様 `YouTubeTranscriptApi.list_transcripts()` から新しい仕様 `ytt_api = YouTubeTranscriptApi(); ytt_api.list()` に更新
- **詳細モード機能**: `--detail` フラグによる詳細テキスト生成機能の実装
- **エントリポイント**: `to_tube_summary_detail.bat` の作成
- **HTML出力拡張**: 詳細セクションと「詳細に飛ぶ」リンクの実装

### 🔧 技術的修正事項
- `youtube_transcript_downloader.py:257`: APIコール方法を新しい仕様に対応
- 動作確認済み: 字幕取得、詳細テキスト生成、HTML出力が正常に動作

## 現状の理解

### 既存システム
- **エントリポイント**: `to_tube_summary.bat` → `youtube_transcript_downloader.py`
- **詳細版エントリポイント**: `to_tube_summary_detail.bat` → `youtube_transcript_downloader.py --detail`
- **処理フロー**:
  1. YouTubeURLからvideoIDを取得
  2. 字幕をVTTファイルとしてダウンロード（youtube-transcript-api 1.2.1使用）
  3. `ret_youyaku_html.py`で要約HTMLを生成
  4. 詳細モードの場合、詳細テキストも生成
  5. ストーリーボード画像をスライスして表示
  6. HTMLをブラウザで開く

### 現在の関数構成
- `youtube_transcript_downloader.py:process_video()`: メイン処理
- `ret_youyaku_html.py:do()`: 要約HTML生成（詳細モード対応済み）
- `ret_youyaku_html.py:yoyaku_gemini()`: Gemini APIで要約生成
- `ret_youyaku_html.py:generate_detail_text()`: 詳細テキスト生成

## 実装された機能の詳細

### 詳細テキスト生成機能
- `ret_youyaku_html.py`に`generate_detail_text()`関数を実装
- gemini-2.0-flashモデルを使用して詳細テキストを生成
- 字幕ファイルを整形し、読みやすい日本語の文章に変換

### HTML出力の拡張
- `txt_to_html()`関数で詳細モード対応
- HTMLの上部に「詳細に飛ぶ」リンクを追加
- 既存の要約の後に詳細セクションを追加
- 詳細セクションはMarkdownからHTMLに変換

### 新しいエントリポイント
- `to_tube_summary_detail.bat`を作成
- `youtube_transcript_downloader.py`で`--detail`フラグを処理
- 詳細モードの場合のみ詳細テキスト生成を実行

## 依存関係とAPIバージョン

### 重要な技術的更新
- **youtube-transcript-api**: バージョン1.2.1に対応済み
  - 旧API: `YouTubeTranscriptApi.list_transcripts(video_id)`
  - 新API: `ytt_api = YouTubeTranscriptApi(); ytt_api.list(video_id)`
- **Geminiモデル**: gemini-2.0-flashを使用
- **Python要件**: 3.8以上

### 関数の共有
- `configure_gemini()`関数を共有
- `read_vtt()`関数を共有
- HTMLテンプレート部分を共有

## 今後のメンテナンス考慮事項

### APIバージョン管理
- youtube-transcript-api の新しいバージョンリリース時の対応方法
- Gemini APIの仕様変更への対応
- 互換性テストの実行方法

### ファイル構成の原則
- 新しいファイルは最小限に抑制
- 既存ファイルの修正は機能追加のみ
- 後方互換性を維持