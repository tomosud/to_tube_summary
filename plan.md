# Structured Outputs実装計画

## 現状分析

### 現在の実装
- `ret_youyaku_html.py`のGemini要約処理で通常のテキストレスポンスを使用
- Markdownテキストをパースして時間分散をチェック
- 不適切な場合はリトライ処理を実行
- HTML生成時に正規表現でタイムスタンプを抽出・整形

### 問題点
- フォーマットが不安定
- 見出しの時間抽出に失敗することがある
- 本文の文字数制限が不確実

## Structured Outputs実装方針

### 1. JSONスキーマ設計
```json
{
  "type": "OBJECT",
  "required": ["title", "summary", "sections"],
  "properties": {
    "title": {"type": "STRING"},
    "summary": {"type": "STRING"},
    "sections": {
      "type": "ARRAY",
      "items": {
        "type": "OBJECT",
        "required": ["heading", "timestamp_seconds", "content"],
        "properties": {
          "heading": {"type": "STRING"},
          "timestamp_seconds": {"type": "INTEGER"},
          "content": {
            "type": "STRING",
            "description": "最大150文字程度の本文"
          }
        }
      }
    }
  }
}
```

### 2. 実装手順

#### Phase 1: Structured Outputs対応
- `yoyaku_gemini`関数を更新
- Gemini APIのStructured Outputs機能を実装
- JSONスキーマを定義

#### Phase 2: レスポンス処理更新
- JSON形式のレスポンスを処理する新しい関数を作成
- 時間分散チェック機能をJSONデータに対応
- HTML生成ロジックを更新

#### Phase 3: 品質向上
- 文字数制限の確実な実装
- タイムスタンプの精度向上
- エラーハンドリング強化

### 3. 技術的詳細

#### Gemini APIコール変更
```python
response = client.models.generate_content(
    model='gemini-2.0-flash',
    contents=prompt,
    config={
        'response_mime_type': 'application/json',
        'response_schema': schema
    }
)
```

#### JSON処理
- タイムスタンプを秒数で取得
- 文字数制限を確実に適用
- 見出しと本文の構造化

#### 品質保証
- JSON形式による確実なパース
- タイムスタンプの数値型による正確な処理
- 文字数制限の厳密な適用

### 4. 移行戦略

1. 新しい関数を作成し、既存機能を保持
2. テスト実行で動作確認
3. 既存の`yoyaku_gemini`関数を更新
4. 不要なコードを削除

### 5. 期待される改善効果

- **フォーマット安定性**: JSON構造による確実なデータ取得
- **タイムスタンプ精度**: 数値型による正確な時間処理
- **文字数制御**: 150文字制限の確実な適用
- **保守性向上**: 構造化されたデータ処理によるコードの簡素化