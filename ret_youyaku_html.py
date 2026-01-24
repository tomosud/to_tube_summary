import os
import re
from openai import OpenAI
import tkinter as tk
from tkinter import simpledialog

def get_api_key():
    """APIキーを取得または設定する"""
    api_key_file = "api_key.txt"

    # ファイルが存在する場合はそこからAPIキーを読み込む
    if os.path.exists(api_key_file):
        with open(api_key_file, "r") as f:
            return f.read().strip()

    # ファイルが存在しない場合はダイアログを表示して入力を求める
    root = tk.Tk()
    root.withdraw()  # メインウィンドウを非表示

    api_key = simpledialog.askstring(
        "API Key 設定",
        "OpenAI APIキーを入力してください：\n（入力されたキーはapi_key.txtに保存されます）"
    )

    if api_key:
        # APIキーをファイルに保存
        with open(api_key_file, "w") as f:
            f.write(api_key)
        return api_key
    else:
        raise ValueError("APIキーが設定されていません。")

# APIキーを設定
apikey = get_api_key()
print('---apikey set!')

# OpenAIクライアントを初期化
client = OpenAI(api_key=apikey)

# 使用するモデル（環境変数から取得、デフォルトはgpt-5.2）
MODEL_NAME = os.environ.get('OPENAI_MODEL', 'gpt-5.2-2025-12-11')

# トークン使用量の累計
total_usage = {'input': 0, 'output': 0}

def count_tokens(response):
    """APIレスポンスからトークン数を取得して累計に加算"""
    usage = response.usage
    input_tokens = usage.prompt_tokens
    output_tokens = usage.completion_tokens

    # 累計に加算
    total_usage['input'] += input_tokens
    total_usage['output'] += output_tokens

    return input_tokens, output_tokens

def print_token_summary():
    """トークン使用量の累計を表示"""
    input_tok = total_usage['input']
    output_tok = total_usage['output']

    # 通常モデル（入力$1.75/1M、出力$14.00/1M）
    normal_cost = (input_tok / 1_000_000) * 1.75 + (output_tok / 1_000_000) * 14.00
    # 安価モデル（入力$0.25/1M、出力$2.00/1M）
    cheap_cost = (input_tok / 1_000_000) * 0.25 + (output_tok / 1_000_000) * 2.00

    print(f"\n=== API使用量サマリー ===")
    print(f"入力トークン: {input_tok:,}")
    print(f"出力トークン: {output_tok:,}")
    print(f"合計トークン: {input_tok + output_tok:,}")
    print(f"価格目安: 通常モデル ${normal_cost:.4f} / 安価モデル ${cheap_cost:.4f}")

# グローバル変数
url_base = ""

def get_vtt_duration_in_seconds(vtt_lines):
    last_time = None
    timecode_pattern = re.compile(r'(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s-->\s(\d{2}):(\d{2}):(\d{2})\.(\d{3})')

    for line in vtt_lines:
        match = timecode_pattern.match(line.strip())
        if match:
            # 終了時刻を抽出
            h, m, s, ms = map(int, match.groups()[4:])
            last_time = h * 3600 + m * 60 + s + ms / 1000.0

    if last_time is not None:
        return int(last_time)  # 整数に変換（小数点以下は切り捨て）
    else:
        return 0  # タイムコードが見つからない場合
    
#見出しの時間が良い分散になっているかを確認する関数
def judge_good_time_split(text_lines,vtt_lines):
    # ---------------------- 正規表現 ---------------------- #
    ts_pattern = re.compile(r"(?:([0-9]+)時間)?(?:([0-9]+)分)?([0-9]+)秒頃")

    def parse_timestamp(text):
        m = ts_pattern.search(text)
        if not m:
            return None
        h = int(m.group(1) or 0)
        mnt = int(m.group(2) or 0)
        s = int(m.group(3))
        return h * 3600 + mnt * 60 + s

    def format_time(sec):
        """秒数を「X分Y秒」形式に変換"""
        m, s = divmod(sec, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}時間{m}分{s}秒"
        return f"{m}分{s}秒"

    all_time = []
    time_and_headings = []  # 時間と見出しのペア
    for line in text_lines:
        # 時間情報を抽出
        match = re.search(r"(\d+)分(\d+)秒頃", line)
        if match:
            ts = parse_timestamp(line)
            all_time.append(ts)
            time_and_headings.append((ts, line.strip()))

    vttsec = get_vtt_duration_in_seconds(vtt_lines)

    if not all_time:
        print('タイムスタンプが見つかりません。')
        return False

    per = float(all_time[-1]) / float(vttsec)

    def print_time_headings():
        """時間と見出しを表示"""
        print(f"  動画の長さ: {format_time(vttsec)} ({vttsec}秒)")
        print(f"  最後の見出し時間: {format_time(all_time[-1])} ({all_time[-1]}秒)")
        print(f"  カバー率: {per*100:.1f}%")
        print("  --- 見出し一覧 ---")
        for ts, heading in time_and_headings:
            # 見出しを短く表示（最大60文字）
            short_heading = heading[:60] + "..." if len(heading) > 60 else heading
            print(f"    {format_time(ts):>12} | {short_heading}")

    if len(all_time) != len(list(set(all_time))):
        print('時間が重複している行があります。')
        print_time_headings()
        return False
    if per < 0.5:
        print('時間の分散が不均一です。')
        print_time_headings()
        return False

    return True

def yoyaku_gemini(vtt, title, output_html_path, images=None, detail_text=None, thumbnail_path=None):
    """字幕ファイルを要約してHTMLを生成する"""
    result_merged_txt = read_vtt(vtt)

    # VTTエントリをパース（展開可能な字幕表示用）
    vtt_entries = parse_vtt_with_timestamps(result_merged_txt)

    print(f'要約中（モデル: {MODEL_NAME}）')

    
    add = (
    "これは.vtt形式の字幕ファイルです。字幕の時刻を正確に解釈し、Markdownで要約してください。"
    "時間の読み取りミスは重大なので、タイムスタンプは必ず正確に処理してください。\n"
    "\n"
    "【重要】タイムスタンプのルール：\n"
    "- 各見出しには、その話題が実際に話された時刻を**必ず1つだけ**付けてください。\n"
    "- 形式は「動画：*分*秒頃」とし、例として 00:16:27.182 は「動画：16分27秒頃」となります。\n"
    "- **絶対に複数の時間を書かないでください**（例：「0分55秒頃／11分10秒頃」は禁止）。\n"
    "- **同じ時間を複数の見出しに使わないでください**。各見出しは固有の時間を持つ必要があります。\n"
    "- 見出しの時間は**時系列順（昇順）**に並べてください。後の見出しが前の見出しより早い時間になってはいけません。\n"
    "- 同じ時間帯に複数の話題がある場合は、1つの見出しに統合するか、数秒ずらして区別してください。\n"
    "- 総括・まとめセクションも、その話題が話された時刻（通常は動画の終盤）を1つだけ記載してください。\n"
    "\n"
    "【目的】このタイムスタンプは、見出しごとに字幕を分割表示するために使用します。\n"
    "各見出しの時間から次の見出しの時間までの字幕が、その見出しに紐づけられます。\n"
    "そのため、時間が正確で、時系列順であることが非常に重要です。\n"
    "\n"
    "タイムスタンプは字幕の全発話に機械的に付けず、"
    "複数字幕をまとめた話題では、次の基準で最も代表的な時刻を1つ選んでください：\n"
    "- その話題が明確に始まった時刻\n"
    "- または、要点／結論が最初に示された時刻\n"
    "\n"
    "要約が長くなる場合は、動画全体の時間の流れを俯瞰し、"
    "見出しが特定の時間帯に偏りすぎないように構成を調整してください。"
    "同じ時間帯に話題が密集して見出しが増えすぎる場合は、"
    "無理に細分化せず統合して、話題ごとの代表時刻が自然に分散するようにしてください。\n"
    )

    add += f'タイトルは「{title}」を日本語に訳して使用してください。\n'

    add += (
        "手順や複数の項目を詳しく説明する場合、"
        "タイムスタンプ付きの項目は必ず見出し（###または####）として記載してください。\n"
        "タイムスタンプは見出しの末尾に括弧で含めてください（次の形式に統一）：\n"
        "### 話題名（動画：*分*秒頃）\n"
        "\n"
        "例:\n"
        "### 鱗の除去（動画：5分50秒頃）\n"
        "スーパーの切り身は鱗が残っていることが多いので、食感を損ねないように丁寧に取り除く。\n\n"
        "### 小骨の除去（動画：6分11秒頃）\n"
        "中骨に沿って並ぶ小骨を丁寧に抜き取る。\n\n"
        "このように、タイムスタンプを含む項目は見出しとして独立させ、"
        "説明文は見出しの下に配置してください。"
        "説明文がない場合でも、見出しだけは記載してください。\n"
    )

    f1text = (
        "あなたは、字幕ファイルから話された時間を正しく認識し、正確で読みやすい要約を作るスペシャリストです。"
        "以下の内容を、日本語で、元の文章の**およそ1/2から2/3程度**の文字数を目安に、**詳細に要約**してMarkdown形式で出力してください"
        "（ただし全体で1万字を超えないこと）。"
        "文章は敬体ではなく常体で書いてください。"
        "字幕には誤字が含まれている可能性があるため、文意に基づいて適切に修正してください。"
        "内容を省略しすぎず、**結論に至るまでの主要な論拠や理由、具体的な事例、重要な専門用語**を記述し、情報量を充実させてください。"
        "各話題の**結論だけでなく、その過程や背景**も残してください。"
        "特に重要なポイントは、**箇条書き（リスト）**を積極的に利用して整理してください。"
        "文字数が増えても、話題の結論まで書いてください。"
        "一目で構造が把握できるように、見出し（大見出し・小見出し）を適切に付けてください。"
        "見出しだけ読んでも、内容の流れがわかるように工夫してください。"
        "内容が多すぎる場合は最初から計画して見出しを分割したり、適切に改行や段落分けを行って、読みやすい文章にしてください。"
        f"{add}"
        "この指示への返答は不要です。出力は内容のみを表示し、最後に「以上」と記載してください。\n\n"
    )


    f1text += '\n'.join(result_merged_txt)

    # OpenAI APIでチャット履歴を管理
    messages = []

    while True:
        # 最初のメッセージを送信
        messages = [{"role": "user", "content": f1text}]

        responseA = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages
        )

        # トークン数を記録
        in_tok, out_tok = count_tokens(responseA)
        print(f"  要約: 入力 {in_tok:,} / 出力 {out_tok:,} トークン")

        responseA_text = responseA.choices[0].message.content

        #見出しの時間が良い分散になっているかを確認
        if judge_good_time_split(responseA_text.split('\n'), result_merged_txt):
            # 成功したらアシスタントの応答を履歴に追加
            messages.append({"role": "assistant", "content": responseA_text})
            break  # 成功したらループ終了
        else:
            print('分散が悪いので、再度要約を実行します。')
            # 不適切なら新しくセッションを作り直す（messagesをリセット）

    # 回答を踏まえた次の質問
    messages.append({
        "role": "user",
        "content": "では、その内容の興味深いポイントをまとめて。200文字程度で日本語で。「動画のポイント」という見出しを付けて。この講演に興味を持つ人が特記したいような内容を。全般的でなくとも、特徴的な点を。またこっちは文末に「以上」は不要。"
    })

    responseB = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages
    )

    # トークン数を記録
    in_tok, out_tok = count_tokens(responseB)
    print(f"  ポイント: 入力 {in_tok:,} / 出力 {out_tok:,} トークン")

    responseB_text = responseB.choices[0].message.content

    result = responseB_text.split('\n') + ['\n'] + [url_base] + responseA_text.split('\n')

    # HTMLファイルを生成
    txt_to_html(result, output_html_path, url_base, images, detail_text, thumbnail_path, vtt_entries)

def extract_timestamp(line):
    """行から時間情報を抽出する"""
    match = re.search(r"(\d+)分(\d+)秒頃", line)
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        return minutes * 60 + seconds
    return None

def find_matching_images(current_time, next_time, images):
    """指定した時間範囲内の画像を取得する"""
    if not images:
        return []
    
    # 次の見出しの時間が指定されていない場合は、現在時刻から5分後までを範囲とする
    end_time = next_time if next_time is not None else current_time + 300
    
    # 現在の見出しから次の見出しまでの時間範囲内の画像を探す
    matching_images = []
    for image in images:
        filepath, img_start_time, img_end_time = image
        # 画像の時間範囲が見出しの時間範囲と重なっているかチェック
        if (img_start_time <= end_time and img_end_time >= current_time):
            matching_images.append((filepath, img_start_time, img_end_time))
    
    # 時間でソート
    matching_images.sort(key=lambda x: x[1])
    
    # 画像が6枚未満の場合、前後の時間帯も含めて探す
    if len(matching_images) < 6:
        window_seconds = 60  # 1分
        extended_matches = []
        for image in images:
            filepath, img_start_time, img_end_time = image
            if (img_start_time <= current_time + window_seconds and 
                img_end_time >= current_time - window_seconds and
                (filepath, img_start_time, img_end_time) not in matching_images):
                extended_matches.append((filepath, img_start_time, img_end_time))
        
        # 追加の画像も時間でソート（現在時刻からの距離で）
        extended_matches.sort(key=lambda x: abs(x[1] - current_time))
        
        # 必要な数だけ追加
        remaining_slots = 6 - len(matching_images)
        matching_images.extend(extended_matches[:remaining_slots])
        
        # 最終的な時間順でソート
        matching_images.sort(key=lambda x: x[1])
    
    return matching_images[:6]  # 最大6枚まで表示

def get_html_header():
    """HTMLヘッダーを生成する"""
    return [
        "<html>",
        "<head><meta charset='utf-8'>",
        "<style>",
        "body{font-family:sans-serif;line-height:1.7em;padding:1em;background:#121212;color:#fff}",
        "h1,h2,h3,h4{color:#ff9800;border-bottom:1px solid #333;padding-bottom:.3em;margin-top:1.5em}",
        "ul{margin-left:1.5em}",
        "li{margin-bottom:.3em}",
        "p{margin-top:.8em}",
        "a{color:#4fc3f7;text-decoration:none}",
        ".timestamp-section{margin:1.5em 0}",
        ".timestamp-images{display:grid;grid-template-columns:repeat(6,1fr);gap:16px;margin-top:.8em}",
        ".thumb-container{position:relative;width:100%;aspect-ratio:16/9}",
        ".thumb-container:hover{transform:scale(1.875);z-index:100}",
        ".video-preview{position:absolute;top:0;left:0;width:100%;height:100%;border:none;border-radius:4px;display:none}",
        ".video-preview.active{display:block}",
        ".thumb-overlay{position:absolute;top:0;left:0;width:100%;height:100%;display:flex;align-items:center;justify-content:center;background-size:cover;background-position:center;border-radius:4px;cursor:pointer;transition:opacity 0.3s}",
        ".thumb-overlay::after{content:'▶ Click to play';color:rgba(255,255,255,0.3);font-size:14px;background:rgba(0,0,0,0.3);padding:8px 16px;border-radius:4px}",
        ".thumb-container:hover .thumb-overlay::after{opacity:0}",
        ".thumb-overlay.hidden{display:none}",
        ".jump-link{background:#333;padding:10px;margin:10px 0;border-radius:5px;text-align:center}",
        ".detail-section{border-top:2px solid #666;margin-top:2em;padding-top:2em}",
        ".video-thumbnail{max-width:640px;width:100%;border-radius:8px;margin:1em 0;box-shadow:0 4px 8px rgba(0,0,0,.3)}",
        "details.subtitle-toggle{margin:1em 0;background:#1e1e1e;border-radius:6px;border:1px solid #333}",
        "details.subtitle-toggle summary{cursor:pointer;padding:8px 12px;color:#aaa;font-size:0.9em;user-select:none}",
        "details.subtitle-toggle summary:hover{color:#fff;background:#2a2a2a}",
        "details.subtitle-toggle[open] summary{border-bottom:1px solid #333}",
        ".subtitle-content{padding:12px 16px;color:#ccc;font-size:0.9em;line-height:1.8em;white-space:pre-wrap;max-height:400px;overflow-y:auto}",
        "</style>",
        "</head>",
        "<body>"
    ]

def markdown_to_html(text):
    """MarkdownテキストをHTMLに変換する"""
    lines = text.split('\n')
    html_lines = []
    in_list = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 見出し
        if line.startswith('#'):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            level = min(len(line) - len(line.lstrip('#')), 4)
            heading_text = line.lstrip('#').strip()
            html_lines.append(f"<h{level}>{heading_text}</h{level}>")
        # リスト項目
        elif line.startswith('*') or line.startswith('-'):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            item_text = line.lstrip('*-').strip()
            item_html = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", item_text)
            # 対応しない単独の**を除去
            item_html = re.sub(r"\*\*", "", item_html)
            html_lines.append(f"<li>{item_html}</li>")
        # 通常の段落
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            replaced = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", line)
            # 対応しない単独の**を除去
            replaced = re.sub(r"\*\*", "", replaced)
            html_lines.append(f"<p>{replaced}</p>")
    
    if in_list:
        html_lines.append("</ul>")
    
    return '\n'.join(html_lines)

def txt_to_html(lines, output_html_path, urlbase: str = "", images=None, detail_text=None, thumbnail_path=None, vtt_entries=None):
    """Markdown ライクなテキストを HTML に変換（バグフィックス版）

    - 見出し / 本文 → 画像 → リンク の順序を保証
    - タイムスタンプ表記は
        * 3時間4分5秒頃
        * 10分5秒頃
        * 5秒頃         ← 分が省略されている場合は 0分と解釈
    - **…** を正しく <b>…</b> に変換（\1 が残るバグ修正）
    - 中身の無いリスト項目（例: "* **"）を無視
    - 末尾で元テキストを .txt としても保存
    - thumbnail_path: サムネイル画像のパス（タイトル下に表示）
    - vtt_entries: parse_vtt_with_timestamps()の戻り値（展開可能な字幕表示用）
    """

    # ---------------------- HTML テンプレート ---------------------- #
    html_lines = get_html_header()

    # ---------------------- サムネイル画像をページ最上部に表示 ---------------------- #
    if thumbnail_path and os.path.exists(thumbnail_path):
        rel = os.path.relpath(thumbnail_path, os.path.dirname(output_html_path)).replace('\\', '/')
        html_lines.append(f'<img src="{rel}" class="video-thumbnail" alt="Video Thumbnail">')

    # 詳細セクションへのジャンプリンクを追加（詳細テキストがある場合のみ）
    if detail_text:
        html_lines.extend([
            "<div class='jump-link'>",
            "<a href='#detail-section'>📄 詳細に飛ぶ</a>",
            "</div>"
        ])

    # ---------------------- 正規表現 ---------------------- #
    ts_pattern = re.compile(r"(?:([0-9]+)時間)?(?:([0-9]+)分)?([0-9]+)秒頃")

    def parse_timestamp(text: str):
        m = ts_pattern.search(text)
        if not m:
            return None
        h = int(m.group(1) or 0)
        mnt = int(m.group(2) or 0)
        s = int(m.group(3))
        return h * 3600 + mnt * 60 + s

    def format_timestamp(sec: int):
        h, rem = divmod(sec, 3600)
        mnt, s = divmod(rem, 60)
        if h:
            return f"{h}時間{mnt}分{s:02d}秒頃"
        return f"{mnt}分{s:02d}秒頃"

    def build_image_block(match_list):
        buf = ["<div class='timestamp-images'>"]
        for path, img_start, _ in match_list:
            rel = os.path.relpath(path, os.path.dirname(output_html_path)).replace('\\', '/')
            start_sec = int(img_start)
            # urlbaseからvideo_idを抽出（例: https://www.youtube-nocookie.com/watch?v=7D0nWcBQyFE&t= → 7D0nWcBQyFE）
            video_id_match = re.search(r'[?&]v=([a-zA-Z0-9_-]+)', urlbase)
            video_id = video_id_match.group(1) if video_id_match else ''
            embed_url = f"https://www.yout-ube.com/watch?v={video_id}&t={start_sec}&autoplay=1&mute=1"
            click_url = f"{urlbase}{start_sec}"
            buf.append(
                f'<div class="thumb-container">'
                f'<iframe class="video-preview" src="" data-src="{embed_url}" allow="autoplay; encrypted-media; accelerometer; gyroscope; picture-in-picture" allowfullscreen></iframe>'
                f'<div class="thumb-overlay" style="background-image:url(\'{rel}\')" data-click-url="{click_url}" title="クリックして再生 / Ctrl+クリックで動画ページを開く"></div>'
                f'</div>'
            )
        buf.append("</div>")
        return "\n".join(buf)

    # ---------------------- 全タイムスタンプを収集 ---------------------- #
    timestamps = [(idx, parse_timestamp(raw)) for idx, raw in enumerate(lines) if parse_timestamp(raw) is not None]

    # ---------------------- セクションバッファ ---------------------- #
    current = {"heading": "", "body": [], "images": "", "link": "", "subtitle": ""}

    def flush():
        nonlocal current
        if not any(current.values()):
            return
        html_lines.append("<div class='timestamp-section'>")
        if current["heading"]:
            html_lines.append(current["heading"])
        if current["body"]:
            html_lines.extend(current["body"])
        if current["images"]:
            html_lines.append(current["images"])
        if current["link"]:
            html_lines.append(current["link"])
        if current["subtitle"]:
            html_lines.append(current["subtitle"])
        html_lines.append("</div>")
        current = {"heading": "", "body": [], "images": "", "link": "", "subtitle": ""}

    in_list = False

    # ---------------------- メインループ ---------------------- #
    for idx, raw in enumerate(lines):
        line = raw.rstrip()
        if not line:
            continue

        # ----- 見出し ----- #
        m_h = re.match(r'^(#{1,4})\s*(.+)$', line)
        if m_h:
            flush()
            level = min(len(m_h.group(1)), 4)
            heading_text = m_h.group(2).strip()
            current["heading"] = f"<h{level}>{heading_text}</h{level}>"
            ts_sec = parse_timestamp(heading_text)
            if ts_sec is not None:
                next_sec = next((sec for i2, sec in timestamps if i2 > idx), None)
                if images:
                    imgs = find_matching_images(ts_sec, next_sec, images)
                    if imgs:
                        current["images"] = build_image_block(imgs)
                current["link"] = f'<p><a href="{urlbase}{ts_sec}" target="_blank">▶ 動画：{format_timestamp(ts_sec)}</a></p>'
                # 展開可能な字幕を追加
                if vtt_entries:
                    subtitle_text = get_subtitle_for_range(vtt_entries, ts_sec, next_sec)
                    if subtitle_text:
                        escaped_text = subtitle_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                        current["subtitle"] = f"<details class='subtitle-toggle'><summary>字幕</summary><div class='subtitle-content'>{escaped_text}</div></details>"
            continue

        # ----- タイムスタンプ単独行 ----- #
        ts_sec_inline = parse_timestamp(line)
        ts_only_line = bool(re.fullmatch(r"(?:動画[:：]?\s*)?(?:[0-9]+時間)?(?:[0-9]+分)?[0-9]+秒頃", line))
        if ts_only_line and ts_sec_inline is not None:
            next_sec = next((sec for i2, sec in timestamps if i2 > idx), None)
            if images:
                imgs = find_matching_images(ts_sec_inline, next_sec, images)
                if imgs:
                    current["images"] = build_image_block(imgs)
            current["link"] = f'<p><a href="{urlbase}{ts_sec_inline}" target="_blank">▶ 動画：{format_timestamp(ts_sec_inline)}</a></p>'
            # 展開可能な字幕を追加
            if vtt_entries:
                subtitle_text = get_subtitle_for_range(vtt_entries, ts_sec_inline, next_sec)
                if subtitle_text:
                    escaped_text = subtitle_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    current["subtitle"] = f"<details class='subtitle-toggle'><summary>字幕</summary><div class='subtitle-content'>{escaped_text}</div></details>"
            continue

        # ----- リスト項目内のタイムスタンプ付き項目を見出し化 ----- #
        # パターン: "1. **タイトル（動画：6分11秒頃）**: 本文"
        # または: "* **タイトル（動画：6分11秒頃）**"
        # または: "- **タイトル（動画：6分11秒頃）**: 本文"
        list_item_match = re.match(
            r'^[\s*\-0-9.]+\*\*([^*]+（動画[:：]?\s*(?:[0-9]+時間)?(?:[0-9]+分)?[0-9]+秒頃）)\*\*(?:[:：]?\s*(.*))?$',
            line
        )
        if list_item_match:
            flush()
            heading_text = list_item_match.group(1).strip()
            body_text = list_item_match.group(2).strip() if list_item_match.group(2) else None

            # 小見出しとして処理（h4レベル）
            current["heading"] = f"<h4>{heading_text}</h4>"

            # タイムスタンプを抽出して画像とリンクを生成
            ts_sec = parse_timestamp(heading_text)
            if ts_sec is not None:
                next_sec = next((sec for i2, sec in timestamps if i2 > idx), None)
                if images:
                    imgs = find_matching_images(ts_sec, next_sec, images)
                    if imgs:
                        current["images"] = build_image_block(imgs)
                current["link"] = f'<p><a href="{urlbase}{ts_sec}" target="_blank">▶ 動画：{format_timestamp(ts_sec)}</a></p>'
                # 展開可能な字幕を追加
                if vtt_entries:
                    subtitle_text = get_subtitle_for_range(vtt_entries, ts_sec, next_sec)
                    if subtitle_text:
                        escaped_text = subtitle_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                        current["subtitle"] = f"<details class='subtitle-toggle'><summary>字幕</summary><div class='subtitle-content'>{escaped_text}</div></details>"

            # 本文があれば追加
            if body_text:
                body_html = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", body_text)
                body_html = re.sub(r"\*\*", "", body_html)
                current["body"].append(f"<p>{body_html}</p>")

            continue

        # ----- 本文 / リスト ----- #
        if line.lstrip().startswith("*"):
            # リスト項目
            if not in_list:
                current["body"].append("<ul>")
                in_list = True
            item_raw = line.lstrip("* ")
            # スキップ: 空 or "**" のみ
            if re.fullmatch(r"\*\*\s*\*\*", item_raw.strip()):
                continue
            item_html = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", item_raw)
            # 対応しない単独の**を除去
            item_html = re.sub(r"\*\*", "", item_html)
            current["body"].append(f"<li>{item_html}</li>")
        else:
            if in_list:
                current["body"].append("</ul>")
                in_list = False
            if line.startswith("http://") or line.startswith("https://"):
                current["body"].append(f'<p><a href="{line}" target="_blank">{line}</a></p>')
            else:
                replaced = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", line)
                # 対応しない単独の**を除去
                replaced = re.sub(r"\*\*", "", replaced)
                current["body"].append(f"<p>{replaced}</p>")

    if in_list:
        current["body"].append("</ul>")
    flush()

    # ---------------------- 詳細セクション追加 ---------------------- #
    if detail_text:
        html_lines.extend([
            "<div id='detail-section' class='detail-section'>",
            "<h2>📄 詳細内容</h2>",
            markdown_to_html(detail_text),
            "</div>"
        ])

    # ---------------------- JavaScript for click to load iframe ---------------------- #
    html_lines.extend([
        "<script>",
        "document.querySelectorAll('.thumb-container').forEach(container => {",
        "  const overlay = container.querySelector('.thumb-overlay');",
        "  const iframe = container.querySelector('.video-preview');",
        "  overlay.addEventListener('click', () => {",
        "    iframe.src = iframe.dataset.src;",
        "    iframe.classList.add('active');",
        "    overlay.classList.add('hidden');",
        "  });",
        "  container.addEventListener('mouseleave', () => {",
        "    iframe.src = '';",
        "    iframe.classList.remove('active');",
        "    overlay.classList.remove('hidden');",
        "  });",
        "});",
        "</script>"
    ])

    # ---------------------- クローズ & テキスト保存 ---------------------- #
    html_lines.append("</body></html>")
    with open(output_html_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(html_lines))
    print(f"✅ HTML 作成: {output_html_path}")

    with open(output_html_path + '.txt', "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines))


def read_vtt(vtt):
    # VTTファイルを読み込む
    with open(vtt, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    #listのまま返す
    result_merged_txt = []

    # 各行を処理
    for line in lines:
        # テキスト行を追加
        result_merged_txt.append(line.strip())

    return result_merged_txt

def parse_vtt_with_timestamps(vtt_lines):
    """VTTファイルをパースして、タイムスタンプとテキストのリストを返す

    Returns:
        list of tuples: [(start_seconds, end_seconds, text), ...]
    """
    # より柔軟な正規表現（1-2桁の時間/分/秒、1-3桁のミリ秒に対応）
    timecode_pattern = re.compile(r'(\d{1,2}):(\d{1,2}):(\d{1,2})[\.,](\d{1,3})\s*-->\s*(\d{1,2}):(\d{1,2}):(\d{1,2})[\.,](\d{1,3})')

    entries = []
    current_start = None
    current_end = None
    current_text_lines = []

    for line in vtt_lines:
        line = line.strip()

        # タイムコード行をチェック
        match = timecode_pattern.match(line)
        if match:
            # 前のエントリがあれば保存
            if current_start is not None and current_text_lines:
                text = ' '.join(current_text_lines).strip()
                if text:
                    entries.append((current_start, current_end, text))

            # 新しいタイムコードを解析
            h1, m1, s1, ms1 = map(int, match.groups()[:4])
            h2, m2, s2, ms2 = map(int, match.groups()[4:])
            current_start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0
            current_end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0
            current_text_lines = []
        elif line and current_start is not None:
            # テキスト行（メタデータ行は除外）
            # WEBVTT、数字のみの行、Kind:、Language:、NOTE などを除外
            if (not line.startswith('WEBVTT') and
                not re.match(r'^\d+$', line) and
                not line.startswith('Kind:') and
                not line.startswith('Language:') and
                not line.startswith('NOTE')):
                current_text_lines.append(line)

    # 最後のエントリを保存
    if current_start is not None and current_text_lines:
        text = ' '.join(current_text_lines).strip()
        if text:
            entries.append((current_start, current_end, text))

    return entries

def get_subtitle_for_range(vtt_entries, start_sec, end_sec):
    """指定した時間範囲の字幕テキストを取得して整形する

    Args:
        vtt_entries: parse_vtt_with_timestamps()の戻り値
        start_sec: 開始秒数
        end_sec: 終了秒数（Noneの場合は最後まで）

    Returns:
        str: 整形された字幕テキスト
    """
    if end_sec is None:
        end_sec = float('inf')

    # 指定範囲のテキストを収集
    texts = []
    for entry_start, _entry_end, text in vtt_entries:
        if entry_start >= start_sec and entry_start < end_sec:
            texts.append(text)

    # 重複を除去しながら結合（YouTubeのスクロール字幕形式に対応）
    merged_texts = []
    for text in texts:
        # 前のテキストと完全に同じなら除去
        if merged_texts and text == merged_texts[-1]:
            continue

        # 前のテキストの末尾と現在のテキストの先頭が重複している場合、重複部分を除去してマージ
        if merged_texts:
            prev_text = merged_texts[-1]
            # 重複部分を探す（前のテキストの末尾と現在のテキストの先頭）
            overlap_found = False
            # 最大で前のテキストの半分程度まで重複をチェック
            max_overlap = min(len(prev_text), len(text), 50)
            for overlap_len in range(max_overlap, 2, -1):
                if prev_text.endswith(text[:overlap_len]):
                    # 重複部分を除いて追加
                    merged_texts[-1] = prev_text + text[overlap_len:]
                    overlap_found = True
                    break
            if overlap_found:
                continue

        merged_texts.append(text)

    # テキストを結合
    raw_text = ' '.join(merged_texts)

    # 整形: 句読点で改行を追加
    formatted_text = format_subtitle_text(raw_text)

    return formatted_text

def format_subtitle_text(text):
    """字幕テキストを整形する（句読点で改行、余分な空白を除去）

    Args:
        text: 生の字幕テキスト

    Returns:
        str: 整形されたテキスト
    """
    # 余分な空白を正規化
    text = re.sub(r'\s+', ' ', text).strip()

    # 日本語の句読点で改行
    text = re.sub(r'。', '。\n', text)
    text = re.sub(r'！', '！\n', text)
    text = re.sub(r'？', '？\n', text)

    # 英語の句読点で改行（文末のみ）
    # ピリオドの後にスペースと大文字、または文末の場合
    text = re.sub(r'\. ', '.\n', text)
    text = re.sub(r'\! ', '!\n', text)
    text = re.sub(r'\? ', '?\n', text)

    # 連続する改行を1つに
    text = re.sub(r'\n+', '\n', text)

    # 各行の前後の空白を除去
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(line for line in lines if line)

    return text

def generate_detail_text(vtt_content, title):
    """VTTファイルから詳細テキストを生成"""
    format_prompt = (
        "字幕ファイルを整形し、 必要なら和訳して、読みやすい日本語の文章にして。"
        "内容は省略せず、ただし誤字や、文意から見て明らかな単語の間違いや、重複はなくして整理して。"
        "見出しを付けて。この指示への返答は不要です。出力は内容のみを表示し、最後に「以上」と記載してください。"
        f"タイトルは「{title}」です。\n\n"
        + '\n'.join(vtt_content)
    )

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": format_prompt}]
        )
        # トークン数を記録
        in_tok, out_tok = count_tokens(response)
        print(f"  詳細テキスト: 入力 {in_tok:,} / 出力 {out_tok:,} トークン")
        return response.choices[0].message.content
    except Exception as e:
        print(f"詳細テキスト生成でエラーが発生しました: {str(e)}")
        return None

def do(vtt_path, video_title, output_dir, url=None, images=None, detail_mode=False, thumbnail_path=None):
    """
    VTTファイルを要約してHTMLを生成する

    Args:
        vtt_path: VTTファイルのパス
        video_title: 動画タイトル
        output_dir: 出力ディレクトリ
        url: 動画のURL（オプション）
        images: 画像情報のリスト（オプション）
        detail_mode: 詳細モードかどうか（オプション）
        thumbnail_path: サムネイル画像のパス（オプション）

    Returns:
        str: 生成されたHTMLファイルのパス
    """
    # パスの正規化
    vtt = vtt_path.replace('\\','/')
    title = video_title
    
    # HTMLファイルのパスを設定
    html_path = os.path.join(output_dir, os.path.splitext(os.path.basename(vtt))[0] + '.html')
    
    # URLをグローバル変数に設定（要約時に使用）
    global url_base
    if url:
        url_base = url

    #no cokkieのため、URLを変換
    url_base = url_base.replace('www.youtube.com/', 'www.yout-ube.com/')
    
    # 詳細テキストを生成（詳細モードの場合のみ）
    detail_text = None
    if detail_mode:
        print('\n詳細テキストを生成中...')
        vtt_content = read_vtt(vtt)
        detail_text = generate_detail_text(vtt_content, title)
    
    yoyaku_gemini(vtt, title, html_path, images, detail_text, thumbnail_path)

    # トークン使用量サマリーを表示
    print_token_summary()

    return html_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        vtt_path = sys.argv[1]
        video_title = sys.argv[2]
        url = sys.argv[3] if len(sys.argv) > 3 else None
        do(vtt_path, video_title, url)
