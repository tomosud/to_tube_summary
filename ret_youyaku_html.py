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
'''

def txt_to_html(lines, output_html_path, urlbase="", images=None):
    html_lines = [ 
        '<html>',
        '<head><meta charset="utf-8">',        '<style>',
        'body { font-family: sans-serif; line-height: 1.7em; padding: 1em; background: #121212; color: #ffffff; }',
        'h1, h2, h3, h4 { color: #ff9800; border-bottom: 1px solid #333; padding-bottom: 0.3em; margin-top: 1.5em; }',
        'ul { margin-left: 1.5em; }',
        'li { margin-bottom: 0.3em; }',
        'p { margin-top: 0.8em; }',
        'a { color: #4fc3f7; text-decoration: none; }','.timestamp-section { margin: 1em 0; }',
        '.timestamp-images { display: grid; grid-template-columns: repeat(6, 1fr); gap: 16px; margin: 1.5em 0; }',        '.timestamp-image { width: 100%; aspect-ratio: 16/9; object-fit: contain; background: #eee; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); transition: transform 0.3s ease, box-shadow 0.3s ease; cursor: pointer; }',
        '.timestamp-image:hover { transform: scale(2); z-index: 10; box-shadow: 0 8px 16px rgba(0,0,0,0.2); border: 2px solid #ff9800; }',
        '.timestamp-images a { display: block; position: relative; }',
        '.timestamp-content { width: 100%; }',
        '</style>',
        '</head>',
        '<body>'
    ]

    # 見出しと時間情報を収集
    timestamps = []
    in_list = False
    
    # 最初にすべての見出しの時間を収集
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        current_time = extract_timestamp(line)
        if current_time is not None:
            timestamps.append((i, current_time))
    
    # HTMLの生成
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        current_time = extract_timestamp(line)
        timestamp_html = ""
        matching_image = None
        
        if current_time is not None:
            # 次の見出しの時間を探す
            next_time = None
            current_index = next((j for j, (idx, _) in enumerate(timestamps) if idx == i), None)
            if current_index is not None and current_index + 1 < len(timestamps):
                next_time = timestamps[current_index + 1][1]
            
            total_seconds = current_time
            jump_url = f"{urlbase}{total_seconds}"
            timestamp_html = f'<p><a href="{jump_url}" target="_blank">▶ 動画リンク</a></p>'
            line = re.sub(r"\*\*(\d+分\d+秒頃)\*\*", r"\1", line)
            # タイムスタンプに対応する画像を探す
            if images:
                image_paths = find_matching_images(total_seconds, next_time, images)
                if image_paths:
                    matching_image = '<div class="timestamp-images">'
                    for image_info in image_paths:
                        # 相対パスに変換
                        path, img_start_time, img_end_time = image_info
                        rel_path = os.path.relpath(
                            path,
                            os.path.dirname(output_html_path)
                        ).replace('\\', '/')
                        
                        # この画像自身の時間に対応するリンクを作成
                        img_jump_url = f"{urlbase}{int(img_start_time)}"
                        
                        # 画像の時間を分と秒に変換
                        img_minutes = int(img_start_time) // 60
                        img_seconds = int(img_start_time) % 60
                        
                        matching_image += f'<a href="{img_jump_url}" target="_blank"><img src="{rel_path}" class="timestamp-image" alt="Screenshot at {img_minutes}:{img_seconds}" title="クリックして{img_minutes}分{img_seconds}秒の動画を開く"></a>'
                    matching_image += '</div>'

        content_html = ""
        
        if line.startswith("####"):
            if in_list:
                content_html += "</ul>"
                in_list = False
            content_html += f"<h4>{line[4:].strip()}</h4>"
        elif line.startswith("###"):
            if in_list:
                content_html += "</ul>"
                in_list = False
            content_html += f"<h3>{line[3:].strip()}</h3>"
        elif line.startswith("## "):
            if in_list:
                content_html += "</ul>"
                in_list = False
            content_html += f"<h2>{line[3:].strip()}</h2>"
        elif line.startswith("# "):
            if in_list:
                content_html += "</ul>"
                in_list = False
            content_html += f"<h1>{line[2:].strip()}</h1>"
        elif line.startswith("*"):
            if not in_list:
                content_html += "<ul>"
                in_list = True
            # 先に最初の*を削除してからテキスト処理
            clean_line = line[1:].strip()
            # 太字の処理
            clean_line = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", clean_line)
            content_html += f"<li>{clean_line}</li>"
        elif line.startswith("http://") or line.startswith("https://"):
            if in_list:
                content_html += "</ul>"
                in_list = False
            content_html += f'<p><a href="{line}" target="_blank">{line}</a></p>'
        elif "**" in line:
            if in_list:
                content_html += "</ul>"
                in_list = False
            line = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", line)
            content_html += f"<p>{line}</p>"
        else:
            if in_list:
                content_html += "</ul>"
                in_list = False
            content_html += f"<p>{line}</p>"

        if matching_image:
            html_lines.append('<div class="timestamp-section">')
            html_lines.append(matching_image)
            html_lines.append('<div class="timestamp-content">')
            html_lines.append(content_html)
            if timestamp_html:
                html_lines.append(timestamp_html)
            html_lines.append('</div></div>')
        else:
            html_lines.append(content_html)
            if timestamp_html:
                html_lines.append(timestamp_html)

    if in_list:
        html_lines.append("</ul>")

    html_lines.append('</body></html>')

    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_lines))

    #deb
    with open(output_html_path + '.txt', "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ HTMLが作成されました: {output_html_path}")
'''

def txt_to_html(lines, output_html_path, urlbase="", images=None):
    """MarkdownライクなリストをHTMLへ変換する関数（改訂版）

    - **表示順序** : 見出し / 本文 → 動画リンク → 画像
    - 画像サムネイルは必ず末尾に配置し、クリックで該当タイムスタンプへジャンプ
    - alt / title 属性にも画像の時刻を入れ、アクセシビリティを向上
    - 行内にタイムスタンプがあっても無くても対応
    """

    # ------------------------------------------------------------------
    # 1. HTML スタブ & CSS
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 2. 全行のタイムスタンプを先に収集
    # ------------------------------------------------------------------
    timestamps = []  # (index, seconds)
    for idx, raw in enumerate(lines):
        m = re.search(r"(\d+)分(\d+)秒頃", raw)
        if m:
            seconds = int(m.group(1)) * 60 + int(m.group(2))
            timestamps.append((idx, seconds))

    # ------------------------------------------------------------------
    # 3. メインループ
    # ------------------------------------------------------------------
    in_list = False
    for idx, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue

        # ---------- 見出し判定 ----------
        heading_html = ""
        m_h = re.match(r'^(#{1,4})\s*(.+)$', line)
        if m_h:
            level = min(len(m_h.group(1)), 4)
            heading_html = f"<h{level}>{m_h.group(2).strip()}</h{level}>"
            if in_list:
                html_lines.append("</ul>")
                in_list = False

        # ---------- タイムスタンプ抽出 ----------
        ts_match = re.search(r"(\d+)分(\d+)秒頃", line)
        current_ts = int(ts_match.group(1))*60 + int(ts_match.group(2)) if ts_match else None
        next_ts = None
        if current_ts is not None:
            for i2, sec in timestamps:
                if i2 > idx:
                    next_ts = sec
                    break

        # ---------- 本文 / リスト ----------
        body_html = ""
        if not m_h:  # 見出し行以外が対象
            if line.startswith("*"):
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                item = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", line.lstrip("*").strip())
                body_html = f"<li>{item}</li>"
            elif line.startswith("http://") or line.startswith("https://"):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                body_html = f'<p><a href="{line}" target="_blank">{line}</a></p>'
            else:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                body_html = f"<p>{re.sub(r'\*\*(.*?)\*\*', r'<b>\\1</b>', line)}</p>"

        # ---------- 動画リンク ----------
        link_html = ""
        if current_ts is not None:
            mm, ss = divmod(current_ts, 60)
            link_html = f'<p><a href="{urlbase}{current_ts}" target="_blank">▶ 動画：{mm}分{ss:02d}秒頃</a></p>'

        # ---------- 画像サムネイル ----------
        images_html = ""
        if current_ts is not None and images:
            matched = find_matching_images(current_ts, next_ts, images)
            if matched:
                buf = ["<div class='timestamp-images'>"]
                for path, img_start, img_end in matched:
                    rel = os.path.relpath(path, os.path.dirname(output_html_path)).replace('\\', '/')
                    mm_i, ss_i = divmod(int(img_start), 60)
                    buf.append(
                        f'<a href="{urlbase}{int(img_start)}" target="_blank">'
                        f'<img src="{rel}" class="timestamp-image" '
                        f'alt="Screenshot at {mm_i}:{ss_i:02d}" '
                        f'title="クリックして{mm_i}分{ss_i:02d}秒の動画を開く"></a>'
                    )
                buf.append("</div>")
                images_html = "\n".join(buf)

        # ---------- セクション出力 ----------
        if heading_html or body_html or link_html or images_html:
            html_lines.append("<div class='timestamp-section'>")
            if heading_html:
                html_lines.append(heading_html)
            if body_html:
                html_lines.append(body_html)
            if link_html:
                html_lines.append(link_html)
            if images_html:
                html_lines.append(images_html)
            html_lines.append("</div>")

    if in_list:
        html_lines.append("</ul>")

    html_lines.append("</body></html>")
    with open(output_html_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(html_lines))
    print(f"✅ HTMLが作成されました: {output_html_path}")




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
