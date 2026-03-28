# YouTube動画要約ツール

Windowsで動作するYouTube動画の要約ツール。YouTubeのURLをクリップボードにコピーして実行すると、動画の字幕を取得・要約し、タイムスタンプ付きのHTMLページを生成する。

要約にはOpenAI APIを使用する。YouTubeのストーリーボードからサムネイル画像もスライスして配置する。

![image](https://github.com/user-attachments/assets/51177fbd-f2d7-4e65-a5b6-998de72b5376)


## 必要なもの

- Windows 10/11
- Python 3.8以上
- OpenAIのAPIキー
  - 初回実行時にダイアログで入力を求められ、`api_key.txt`に保存される
  - 変更したい場合は`api_key.txt`を削除して再実行

## セットアップ

1. このリポジトリをクローンまたはダウンロード
2. `setup.bat`を実行（Python仮想環境の作成と依存パッケージのインストール）


## 使い方

1. YouTubeの動画ページでURLをコピー（クリップボード）
2. 以下のいずれかのバッチファイルを実行

| ファイル名 | モデル | 説明 |
|-----------|--------|------|
| `to_tube_summary.bat` | gpt-5.2-2025-12-11 | 標準版 |
| `to_tube_summary_detail.bat` | gpt-5.2-2025-12-11 | 詳細版（要約＋字幕全文整形） |
| `to_tube_summary_cheep.bat` | gpt-5-mini-2025-08-07 | 安価版（軽量モデル） |

### 別モデルのバッチを追加する

既存batをコピーし、`set OPENAI_MODEL=` の行を変更する。詳細モードは末尾に `--detail` を追加。


## 出力構成

生成されるファイルは `C:\temp\html\[動画タイトル]\` に保存される。

```
[動画タイトル]/
├── index.html        ← 汎用テンプレート（全動画共通）
├── data.js           ← 動画固有データ（URL、セクション、画像パス、字幕等）
├── index.html.txt    ← 要約のMarkdownテキスト（生テキスト保存）
├── info.json         ← 動画メタ情報（タイトル、チャンネル、投稿日等）
├── Thumbnail.jpg     ← 動画サムネイル
├── [タイトル].vtt    ← 字幕ファイル
└── images/           ← ストーリーボードからスライスした画像
```

### index.html と data.js の分離構造

出力HTMLは **汎用テンプレート `index.html`** と **動画固有データ `data.js`** に分離されている。

- `index.html` は `template/index.html` のコピーで、全動画で同一ファイル
- `data.js` は `var PAGE_DATA = { ... };` 形式で動画ごとのデータを格納
- `index.html` は `<script src="data.js">` でデータを読み込むため、`file://` でもスタンドアロンで動作する

**data.js のスキーマ:**

```js
var PAGE_DATA = {
  schema_version: 1,          // データスキーマバージョン
  video_id: "oza36AqcLW8",
  url: "https://www.youtube.com/watch?v=oza36AqcLW8",  // 正規YouTube URL
  thumbnail: "Thumbnail.jpg",
  sections: [
    {
      heading: "セクションタイトル（動画：5分30秒頃）",
      level: 2,
      timestamp: 330,          // 秒数。null if なし
      body: "<p>本文HTML</p>", // Markdown→HTML変換済み
      images: [{ src: "images/xxx.jpg", start: 300, end: 330 }],
      subtitle: "字幕テキスト" // 生テキスト。null if なし
    }
  ],
  detail: "<h2>...</h2>..."    // 詳細モード時のみ。null if なし
};
```

**設計方針:**
- `url` には正規YouTube URL（`www.youtube.com`）を保持する。プロキシURL（`yout-ube.com` 等）への変換はテンプレート側の `CONFIG.proxyDomain` で行う
- ChatGPTリンクの生成もテンプレート側で行う
- `body` はPython側でMarkdown→HTML変換済みの状態で格納する
- `schema_version` でデータの後方互換性を管理する。テンプレートは未知フィールドを無視し、欠損フィールドにはデフォルト値を使う

### 動画の埋め込みについて

テンプレートでは動画リンクにプロキシドメイン `yout-ube.com` を使用している。

- **iframe embed (`youtube-nocookie.com/embed/`)**: エラー153で再生不可のため不採用
- **採用方式**: `https://www.yout-ube.com/watch?v={id}&t={秒数}` の通常URLをiframeで埋め込み。`autoplay` や `mute` パラメータは効かないため付与しない

### サムネイルの動作

各セクションの画像グリッドは以下の挙動で動作する:

1. **通常状態**: ストーリーボードからスライスしたサムネイル画像を6列グリッドで表示。▶マーク付き
2. **ホバー**: サムネイルが1.8倍に拡大（`transform: scale(1.8)`）
3. **クリック**: サムネイルが非表示になり、その場にiframeが埋め込まれて動画再生が始まる。該当タイムスタンプ（`&t=秒数`）から再生される
4. **ホバー外れる**: iframeを破棄して再生停止。サムネイルが元のサイズで復帰する

**YouTube UI肥大化問題への対策:**
サムネイルが小さいグリッド表示のため、iframe内のYouTube UI（チャンネルリンク、タイトル等）が相対的に大きくなり再生ボタンが押せなくなる問題がある。これに対し、iframeを実際の表示領域の2倍サイズ（`width:200%; height:200%`）で描画し、`transform: scale(0.5)` + `transform-origin: top left` で縮小表示することで、YouTube側には大きな画面サイズとして認識させ、UIが適切なサイズになるようにしている。

**検証用ページ:**
`sample/playtest/index.html` に各方式の比較テストページがある。セクション10が採用された方式。


## テンプレートの更新（バージョン管理）

`template/index.html` には `<meta name="template-version" content="N">` が埋め込まれている。

### 自動更新の仕組み

ツール実行のたびに `C:\temp\html` 以下の全フォルダをスキャンし、`data.js` が存在するフォルダで `index.html` のテンプレートバージョンが古い場合、最新テンプレートで自動的に上書きする。`data.js` は一切変更されない。

### テンプレートを変更する手順

1. `template/index.html` を編集（CSS、JS、レイアウト等）
2. `<meta name="template-version" content="N">` の `N` をインクリメント
3. `ret_youyaku_html.py` の `TEMPLATE_VERSION` を同じ値に更新
4. 次にツールを実行すると、過去の全フォルダの `index.html` が自動更新される

### 手動で全フォルダを更新する

ツールを実行せずにテンプレートだけ更新したい場合:

```
python -c "from ret_youyaku_html import update_templates; update_templates(r'C:\temp\html')"
```


## 既存データの移行

旧フォーマット（モノリシックHTML）から新フォーマット（data.js + index.html）への移行:

```
migrate.bat
```

- `data.js` が存在しないフォルダを対象に、`.html.txt`（生テキスト）/ `info.json` / `images/` / `.vtt` から `data.js` を再生成する
- 旧HTMLファイルは `.html.bak` にリネームされる（削除はされない）
- 一度だけの実行で完了する。以降は自動更新のみ


## 配布（GitHub Pages）

`C:\work\script\tube_pages` で GitHub Pages への配布を行っている。

### ワークフロー

1. `to_tube_summary` で生成されたフォルダを `tube_pages/pages/htmls/` に手動コピー
2. `tube_pages/pages/build.bat` を実行（`pages.json` を再生成）
3. `tube_pages/push.bat` で GitHub Pages にデプロイ

### tube_pages との互換性

- `tube_pages/pages/build.py` はフォルダ内の最初の `.html` ファイルを検出する
- ファイル名が `index.html` に変わっても動作に影響はない
- `tube_pages` 側の変更は不要
- テンプレート更新後は、`tube_pages/pages/htmls/` 内のフォルダにも手動で最新 `index.html` をコピーするか、以下を実行:
  ```
  python -c "from ret_youyaku_html import update_templates; update_templates(r'C:\work\script\tube_pages\pages\htmls')"
  ```


## 技術仕様

### 依存パッケージ（requirements.txt）

| パッケージ | 用途 |
|-----------|------|
| youtube-transcript-api | 字幕取得 |
| yt-dlp | ストーリーボード・サムネイル取得 |
| openai | OpenAI API クライアント |
| Pillow | 画像処理（ストーリーボードのスライス） |
| pyperclip | クリップボード操作 |
| requests | HTTP通信 |

### ファイル構成

| ファイル | 役割 |
|---------|------|
| `youtube_transcript_downloader.py` | メインエントリポイント。字幕取得・ストーリーボード処理・要約呼び出し |
| `ret_youyaku_html.py` | OpenAI APIで要約生成、data.js + テンプレート出力、テンプレート更新・移行機能 |
| `template/index.html` | 汎用HTMLテンプレート（バージョン管理付き） |
| `migrate.bat` | 旧フォーマットからの一括移行 |
| `api_key.txt` | OpenAI APIキー（.gitignore対象） |

### モデル設定

環境変数 `OPENAI_MODEL` でモデルを切り替え可能（デフォルト: `gpt-5.2-2025-12-11`）。


## 注意事項

- 字幕のある動画のみ対応（英語・日本語優先、他の言語もフォールバックで対応）
- 処理時間・APIコストは動画の長さに依存する
- `api_key.txt` は `.gitignore` に設定済み。外部に公開しないこと
