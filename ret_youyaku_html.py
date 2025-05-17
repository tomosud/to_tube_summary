import os
import re
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


def yoyaku_gemini(vtt, title, output_html_path, images=None):
    """字幕ファイルを要約してHTMLを生成する"""
    result_merged_txt = read_vtt(vtt)

    print('要約中')

    #------要約分をgeminiで作ってDL
    #add = 'これはvttの字幕ファイルなので、タイムコードの時間を参考に、各見出しの次の行に大体何分何秒の時点で話された話題かを「動画：*分*秒頃」と書いて。例として00:16:27.182は0時間:16分:27秒.182msです。これは正しくないと困るので慎重に読み取って構築を。'

    add = (
    "これは.vtt形式の字幕ファイルです。各見出しの次の行に、"
    "その話題が話されたおおよそのタイムスタンプを「動画：*分*秒頃」という形式で記載してください。"
    "例えば、00:16:27.182 は「動画：16分27秒頃」となります。"
    "時間の読み取りミスは重大なので、正確に処理してください。"
    )

    add += f'タイトルは「{title}」を日本語に訳して使用してください。\n'

    f1text = (
    "あなたは、字幕ファイルから話された時間を正しく認識し、正確で読みやすい要約を作るスペシャリストです。"
    "以下の内容を、日本語で、元の文章のおよそ1/5の文字数を目安に、詳しめに要約してMarkdown形式で出力してください（ただし全体で1万字を超えないこと）。"
    "文章は敬体ではなく常体で書いてください。"
    "内容を省略しすぎず、文字数が増えても、話題の結論まで書いて。一目で構造が把握できるように、見出し（大見出し・小見出し）を付けてください。"
    "見出しだけ読んでも、内容の流れがわかるように工夫してください。適切に改行や、段落分けを行い、読みやすい文章にしてください。"
    f"{add}"
    "英語の人名や固有名詞は原文通りに保ってください。"
    "この指示への返答は不要です。出力は内容のみを表示し、最後に「以上」と記載してください。\n\n"
    )

    f1text += '\n'.join(result_merged_txt)
    #f1text = ("あなたは字幕ファイルから、それがどの時間に話されたかを正しく認識しながら正確で読み易い要約文を作るスペシャリストです。以下を、日本語で5000文字程度で長めに詳しく要約して。ただし、絶対に１万字を超えないこと。英語の人名、固有名詞などはそのまま使って。大小の見出しを付けて一見してわかりやすく。" + add + "絶対に内容を省略しすぎないで。敬体ではない文章が良い。この指示への返事は不要なので、内容だけ返して。最後には「以上」と書いて。\n\n" + '\n'.join(result_merged_txt))


    chat = model.start_chat()

    # 最初の質問
    responseA = chat.send_message(f1text)

    # 回答を踏まえた次の質問
    responseB = chat.send_message("では、その内容の興味深いポイントをまとめて。200文字程度で日本語で。「動画のポイント」という見出しを付けて。この講演に興味を持つ人が特記したいような内容を。全般的でなくとも、特徴的な点を。またこっちは文末に「以上」は不要。")

    result = responseB.text.split('\n') + ['\n'] + [url_base] + responseA.text.split('\n')
    
    # HTMLファイルを生成
    txt_to_html(result, output_html_path, url_base, images)

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
    """Markdown ライクなテキストを HTML に変換 (リファクタリング版)

    セクション単位でまとめてから出力することで、
    **見出し → 本文 → 画像 → リンク** の順序を保証。
    タイムスタンプ専用行は本文を出力せず、同じセクションに画像・リンクだけを追加。
    """

    # ---- HTML テンプレート & CSS ---- #
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

    # ---- 正規表現 ---- #
    ts_pattern = re.compile(r"(\d+)分(\d+)秒頃")

    # ---- セクション用バッファ ---- #
    current = {
        "heading": "",
        "body": [],
        "images": "",
        "link": ""
    }

    def flush_section():
        """現在のセクションを html_lines に書き出す"""
        nonlocal current
        if not (current["heading"] or current["body"] or current["images"] or current["link"]):
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

    # ---- ユーティリティ ---- #
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

    # ---- すべてのタイムスタンプを先に格納 ---- #
    timestamps = []  # (index, seconds)
    for i, raw in enumerate(lines):
        m = ts_pattern.search(raw)
        if m:
            seconds = int(m.group(1))*60 + int(m.group(2))
            timestamps.append((i, seconds))

    # ---- メインループ ---- #
    in_list = False
    for idx, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue

        # 見出しかどうか
        m_h = re.match(r'^(#{1,4})\s*(.+)$', line)
        if m_h:
            # 次のセクションが始まるので flush
            flush_section()
            level = min(len(m_h.group(1)), 4)
            current["heading"] = f"<h{level}>{m_h.group(2).strip()}</h{level}>"
            continue  # 次の行へ

        # タイムスタンプ検出
        ts_match = ts_pattern.search(line)
        current_ts = int(ts_match.group(1))*60 + int(ts_match.group(2)) if ts_match else None
        # 次見出しまでの最初のTS を画像検索範囲の end とする
        next_ts = None
        if current_ts is not None:
            for i2, sec in timestamps:
                if i2 > idx:
                    next_ts = sec
                    break

        # タイムスタンプ単独行か？
        ts_only = bool(re.fullmatch(r"動画[:：]?\s*\d+分\d+秒頃", line) or re.fullmatch(r"\d+分\d+秒頃", line))

        if ts_only:
            # 本文は追加しない。画像 & リンクだけ追加して終わり。
            if images and current_ts is not None:
                imgs = find_matching_images(current_ts, next_ts, images)
                if imgs:
                    current["images"] = build_image_block(imgs)
            if current_ts is not None:
                mm, ss = divmod(current_ts, 60)
                current["link"] = f'<p><a href="{urlbase}{current_ts}" target="_blank">▶ 動画：{mm}分{ss:02d}秒頃</a></p>'
            continue

        # ---- 本文 or リスト ---- #
        if line.startswith("*"):
            if not in_list:
                current["body"].append("<ul>")
                in_list = True
            item = re.sub(r"\*\*(.*?)\*\*", r"<b>\\1</b>", line.lstrip("*").strip())
            current["body"].append(f"<li>{item}</li>")
        else:
            if in_list:
                current["body"].append("</ul>")
                in_list = False
            if line.startswith("http://") or line.startswith("https://"):
                current["body"].append(f'<p><a href="{line}" target="_blank">{line}</a></p>')
            else:
                replaced = re.sub(r"\*\*(.*?)\*\*", r"<b>\\1</b>", line)
                current["body"].append(f"<p>{replaced}</p>")

    # ループ終了時 flush
    if in_list:
        current["body"].append("</ul>")
        in_list = False
    flush_section()

    # クローズ
    html_lines.append("</body></html>")
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_lines))
    print(f"✅ HTML 作成: {output_html_path}")


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
