# 詳細版実装計画

## 現状の理解

### 既存システム
- **エントリポイント**: `to_tube_summary.bat` → `youtube_transcript_downloader.py`
- **処理フロー**:
  1. YouTubeURLからvideoIDを取得
  2. 字幕をVTTファイルとしてダウンロード
  3. `ret_youyaku_html.py`で要約HTMLを生成
  4. ストーリーボード画像をスライスして表示
  5. HTMLをブラウザで開く

### 既存の関数構成
- `youtube_transcript_downloader.py:process_video()`: メイン処理
- `ret_youyaku_html.py:do()`: 要約HTML生成
- `ret_youyaku_html.py:yoyaku_gemini()`: Gemini APIで要約生成

## 追加機能の仕様

### 目標
- 既存の出力HTMLに加えて、より詳細なテキストを追加
- 詳細テキストは`detail_txt`関数の処理を参考にする
- HTMLの最初に「詳細に飛ぶ」リンクを追加

### detail_txt関数の分析
```python
def detail_txt(vtt_path, title):
    # gemini-2.5-flashを使用
    # プロンプト: "字幕ファイルを整形し、読みやすい日本語の文章にして..."
    # 誤字修正、重複削除、見出し付与
    # 出力: Markdown形式の整形テキスト
```

## 実装計画

### ステップ1: 詳細テキスト生成機能の追加
- `ret_youyaku_html.py`に`generate_detail_text()`関数を追加
- `detail_txt`関数のロジックを参考にしたプロンプトを作成
- gemini-2.5-flashモデルを使用して詳細テキストを生成

### ステップ2: HTML出力の拡張
- `txt_to_html()`関数を修正
- HTMLの上部に「詳細に飛ぶ」リンクを追加
- 既存の要約の後に詳細セクションを追加
- 詳細セクションはMarkdownからHTMLに変換

### ステップ3: 新しいエントリポイントの作成
- `to_tube_summary_detail.bat`を作成
- `youtube_transcript_downloader.py`に`--detail`フラグを追加
- 詳細モードの場合のみ詳細テキスト生成を実行

### ステップ4: 既存コードとの統合
- 既存の処理フローを変更せず、追加機能として実装
- 関数の共有を最大化してコード重複を避ける
- エラーハンドリングを適切に実装

## 技術的考慮事項

### 関数の共有
- `configure_gemini()`関数を共有
- `read_vtt()`関数を共有
- HTMLテンプレート部分を共有

### プロンプト設計
- detail_txt関数のプロンプトをベースにする
- 既存の要約とは異なる詳細度で出力
- HTML向けに適切な形式で出力

### ファイル構成
- 新しいファイルは最小限に抑える
- 既存ファイルの修正は機能追加のみ
- 後方互換性を維持

## 実装順序

1. `ret_youyaku_html.py`に詳細テキスト生成機能を追加
2. HTML出力機能を拡張（ジャンプリンク + 詳細セクション）
3. `youtube_transcript_downloader.py`にフラグ処理を追加
4. `to_tube_summary_detail.bat`を作成
5. テスト実行と調整
6. README.mdの更新