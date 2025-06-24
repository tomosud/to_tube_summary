import os
import re
import json
import google.generativeai as genai
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
        "Google APIキーを入力してください：\n（入力されたキーはapi_key.txtに保存されます）"
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

genai.configure(api_key=apikey)

model = genai.GenerativeModel('gemini-2.0-flash')

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
    
    all_time = []
    for line in text_lines:
        # 時間情報を抽出
        match = re.search(r"(\d+)分(\d+)秒頃", line)
        if match:
            all_time.append(parse_timestamp(line))
            #print(all_time[-1],line)

    vttsec = get_vtt_duration_in_seconds(vtt_lines)

    per = float(all_time[-1]) / float(vttsec)

    #print(per,'vttsec:',vttsec,all_time[-1])
    #print (all_time)

    if len(all_time) != len(list(set(all_time))):
        print('時間が重複している行があります。')
        return False
    if per < 0.5:
        print('時間の分散が不均一です。')
        return False
    
    return True

def validate_json_time_distribution(json_data, vtt_lines):
    """JSONデータの時間分散をチェックする"""
    try:
        sections = json_data.get('sections', [])
        if len(sections) < 2:
            return False
            
        # 動画の総時間を取得
        total_seconds = get_vtt_duration_in_seconds(vtt_lines)
        if total_seconds == 0:
            return False
            
        # セクションの時間を取得
        timestamps = [section.get('timestamp_seconds', 0) for section in sections]
        
        # 重複チェック
        if len(timestamps) != len(set(timestamps)):
            print('時間が重複しているセクションがあります。')
            return False
            
        # 最後のタイムスタンプが動画の50%以上かチェック
        if len(timestamps) > 0:
            last_timestamp = max(timestamps)
            coverage_ratio = float(last_timestamp) / float(total_seconds)
            if coverage_ratio < 0.5:
                print(f'時間の分散が不均一です。カバー率: {coverage_ratio:.2f}')
                return False
                
        return True
        
    except Exception as e:
        print(f'時間分散チェックエラー: {str(e)}')
        return False

def format_timestamp_from_seconds(seconds):
    """秒数から時間文字列に変換"""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}時間{m}分{s:02d}秒頃" if h else f"{m}分{s:02d}秒頃"

def build_image_block(match_list, urlbase, output_html_path):
    """画像ブロックを構築"""
    if not match_list:
        return ""
    buf = ["<div class='timestamp-images'>"]
    for path, img_start, _ in match_list:
        rel = os.path.relpath(path, os.path.dirname(output_html_path)).replace('\\', '/')
        mm_i, ss_i = divmod(int(img_start), 60)
        buf.append(
            f'<a href="{urlbase}{int(img_start)}" target="_blank">'
            f'<img src="{rel}" class="timestamp-image" '
            f'alt="Screenshot at {mm_i}:{ss_i:02d}" '
            f'title="クリックして{mm_i}分{ss_i:02d}秒の動画を開く"></a>'
        )
    buf.append("</div>")
    return "\n".join(buf)

def get_html_template():
    """HTMLテンプレートを返す"""
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
        ".timestamp-image{width:100%;aspect-ratio:16/9;object-fit:contain;background:#eee;border-radius:4px;box-shadow:0 2px 4px rgba(0,0,0,.1);transition:transform .3s ease,box-shadow .3s ease;cursor:pointer}",
        ".timestamp-image:hover{transform:scale(2);z-index:10;box-shadow:0 8px 16px rgba(0,0,0,.2);border:2px solid #ff9800}",
        "</style>",
        "</head>",
        "<body>"
    ]

def json_to_html(json_data, output_html_path, urlbase: str = "", images=None):
    """JSONデータをHTMLに変換"""
    html_lines = get_html_template()
    
    # タイトルと要約を追加
    title = json_data.get('title', '動画要約')
    summary = json_data.get('summary', '')
    
    html_lines.append(f"<h1>{title}</h1>")
    if summary:
        html_lines.extend([f"<h2>動画のポイント</h2>", f"<p>{summary}</p>"])
    
    # セクションを処理
    sections = sorted(json_data.get('sections', []), key=lambda x: x.get('timestamp_seconds', 0))
    
    for i, section in enumerate(sections):
        timestamp_seconds = section.get('timestamp_seconds', 0)
        heading = section.get('heading', '見出し')
        content = section.get('content', '')
        
        html_lines.extend([
            "<div class='timestamp-section'>",
            f"<h3>{heading}</h3>",
            f"<p>{content}</p>"
        ])
        
        # 画像を追加
        if images:
            next_timestamp = sections[i + 1].get('timestamp_seconds') if i + 1 < len(sections) else None
            imgs = find_matching_images(timestamp_seconds, next_timestamp, images)
            if imgs:
                html_lines.append(build_image_block(imgs, urlbase, output_html_path))
        
        # 動画リンクを追加
        time_str = format_timestamp_from_seconds(timestamp_seconds)
        html_lines.extend([
            f'<p><a href="{urlbase}{timestamp_seconds}" target="_blank">▶ 動画：{time_str}</a></p>',
            "</div>"
        ])
    
    html_lines.append("</body></html>")
    
    # ファイルに保存
    with open(output_html_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(html_lines))
    print(f"✅ HTML 作成: {output_html_path}")
    
    # JSONデータもテキストファイルとして保存
    with open(output_html_path + '.txt', "w", encoding="utf-8") as fp:
        fp.write(json.dumps(json_data, ensure_ascii=False, indent=2))

def get_response_schema():
    """Structured OutputsのJSONスキーマを返す"""
    return {
        'type': 'OBJECT',
        'required': ['title', 'summary', 'sections'],
        'properties': {
            'title': {'type': 'STRING'},
            'summary': {'type': 'STRING'},
            'sections': {
                'type': 'ARRAY',
                'items': {
                    'type': 'OBJECT',
                    'required': ['heading', 'timestamp_seconds', 'content'],
                    'properties': {
                        'heading': {'type': 'STRING'},
                        'timestamp_seconds': {'type': 'INTEGER'},
                        'content': {
                            'type': 'STRING',
                            'description': '150文字程度の詳細で、結論を省略しない本文（常体で記述、具体的な数値や固有名詞を含む）'
                        }
                    }
                }
            }
        }
    }

def yoyaku_gemini(vtt, title, output_html_path, images=None):
    """字幕ファイルを要約してHTMLを生成する（Structured Outputs版）"""
    result_merged_txt = read_vtt(vtt)

    print('要約中（Structured Outputs使用）')

    # Structured Outputs用のプロンプト  
    prompt = f"""あなたは、字幕ファイルから話された時間を正しく認識し、最後まで欠けのない、正確で読みやすい要約を作るスペシャリストです。

以下のvtt形式の字幕ファイルを分析し、JSON形式で要約を作成してください。

要件：
1. titleは「{title}」を日本語に訳して使用
2. summaryは動画の興味深いポイントを記述
3. sectionsは各セクションの情報を含む配列
   - heading: 一目で内容が分かる短すぎない見出し
   - timestamp_seconds: その話題が話された時刻（秒数）
   - content: 200文字程度の詳細で、結論を省略しない本文（常体で記述、具体的な数値や固有名詞を含む）

注意点：
- 英語の人名や固有名詞は原文通りに保つ
- 時間の読み取りは正確に行う
- contentは詳細に記述し、具体例や数値も含める
- 各セクションの時間は適切に分散させる
- 内容を省略しすぎず、話題の結論や重要なポイントまで含める

字幕データ：
{chr(10).join(result_merged_txt)}"""

    chat = model.start_chat()
    max_retries = 8
    
    for attempt in range(max_retries):
        try:
            response = chat.send_message(
                prompt,
                generation_config={
                    'response_mime_type': 'application/json',
                    'response_schema': get_response_schema()
                }
            )
            
            # JSONレスポンスをパース
            json_data = json.loads(response.text)
            
            # 時間分散チェック
            if validate_json_time_distribution(json_data, result_merged_txt):
                break
            else:
                print(f'時間分散が不適切です。リトライ {attempt + 1}/{max_retries}')
                chat = model.start_chat()
                
        except Exception as e:
            print(f'JSON解析エラー: {str(e)}. リトライ {attempt + 1}/{max_retries}')
            chat = model.start_chat()
            
        if attempt == max_retries - 1:
            raise Exception("Structured Outputs処理が最大リトライ回数に達しました")
    
    # JSONデータからHTMLを生成
    json_to_html(json_data, output_html_path, url_base, images)

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

def txt_to_html(lines, output_html_path, urlbase: str = "", images=None):
    """Markdown ライクなテキストを HTML に変換（バグフィックス版）

    - 見出し / 本文 → 画像 → リンク の順序を保証
    - タイムスタンプ表記は
        * 3時間4分5秒頃
        * 10分5秒頃
        * 5秒頃         ← 分が省略されている場合は 0分と解釈
    - **…** を正しく <b>…</b> に変換（\1 が残るバグ修正）
    - 中身の無いリスト項目（例: "* **"）を無視
    - 末尾で元テキストを .txt としても保存
    """

    # ---------------------- HTML テンプレート ---------------------- #
    html_lines = [
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
        ".timestamp-image{width:100%;aspect-ratio:16/9;object-fit:contain;background:#eee;border-radius:4px;box-shadow:0 2px 4px rgba(0,0,0,.1);transition:transform .3s ease,box-shadow .3s ease;cursor:pointer}",
        ".timestamp-image:hover{transform:scale(2);z-index:10;box-shadow:0 8px 16px rgba(0,0,0,.2);border:2px solid #ff9800}",
        "</style>",
        "</head>",
        "<body>"
    ]

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
            mm_i, ss_i = divmod(int(img_start), 60)
            buf.append(
                f'<a href="{urlbase}{int(img_start)}" target="_blank">'
                f'<img src="{rel}" class="timestamp-image" '
                f'alt="Screenshot at {mm_i}:{ss_i:02d}" '
                f'title="クリックして{mm_i}分{ss_i:02d}秒の動画を開く"></a>'
            )
        buf.append("</div>")
        return "\n".join(buf)

    # ---------------------- 全タイムスタンプを収集 ---------------------- #
    timestamps = [(idx, parse_timestamp(raw)) for idx, raw in enumerate(lines) if parse_timestamp(raw) is not None]

    # ---------------------- セクションバッファ ---------------------- #
    current = {"heading": "", "body": [], "images": "", "link": ""}

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
        html_lines.append("</div>")
        current = {"heading": "", "body": [], "images": "", "link": ""}

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
            item_html = re.sub(r"\*\*(.*?)\*\*", r"<b>\\1</b>", item_raw)
            current["body"].append(f"<li>{item_html}</li>")
        else:
            if in_list:
                current["body"].append("</ul>")
                in_list = False
            if line.startswith("http://") or line.startswith("https://"):
                current["body"].append(f'<p><a href="{line}" target="_blank">{line}</a></p>')
            else:
                replaced = re.sub(r"\*\*(.*?)\*\*", r"<b>\\1</b>", line)
                current["body"].append(f"<p>{replaced}</p>")

    if in_list:
        current["body"].append("</ul>")
    flush()

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

def do(vtt_path, video_title, output_dir, url=None, images=None):
    """
    VTTファイルを要約してHTMLを生成する
    
    Args:
        vtt_path: VTTファイルのパス
        video_title: 動画タイトル
        output_dir: 出力ディレクトリ
        url: 動画のURL（オプション）
        images: 画像情報のリスト（オプション）
    
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
    
    yoyaku_gemini(vtt, title, html_path, images)
    return html_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        vtt_path = sys.argv[1]
        video_title = sys.argv[2]
        url = sys.argv[3] if len(sys.argv) > 3 else None
        do(vtt_path, video_title, url)
