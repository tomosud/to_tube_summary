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
    add = 'これはvttの字幕ファイルなので、タイムコードの時間を参考に、各見出しの次の行に大体何分何秒の時点で話された話題かを「動画：*分*秒頃」と書いて。例として00:16:27.182は0時間:16分:27秒.182msです。これは正しくないと困るので慎重に読み取って構築を。'

    add = add + 'タイトルは「' + title + '」を和訳して使って。\n'

    f1text = ("あなたは字幕ファイルから、それがどの時間に話されたかを正しく認識しながら正確で読み易い要約文を作るスペシャリストです。以下を、日本語で5000文字程度で長めに詳しく要約して。ただし、絶対に１万字を超えないこと。人名、固有名詞などは英語のままで。大小の見出しを付けて一見してわかりやすく。" + add + "絶対に内容を省略しすぎないで。敬体ではない文章が良い。この指示への返事は不要なので、内容だけ返して。最後には「以上」と書いて。\n\n" + '\n'.join(result_merged_txt))

    chat = model.start_chat()

    # 最初の質問
    responseA = chat.send_message(f1text)

    # 回答を踏まえた次の質問
    responseB = chat.send_message("では、その内容の頭に興味深いポイントを足したいのでまとめて。200文字程度で日本語で。「動画のポイント」という見出しを付けて。この講演に興味を持つ人が特記したいような内容を。全般的でなくとも、特徴的な点を。またこっちは文末に「以上」は不要")

    result = responseB.text.split('\n') + ['\n'] + [url_base] + responseA.text.split('\n')
    
    # HTMLファイルを生成
    txt_to_html(result, output_html_path, url_base, images)

def find_matching_images(timestamp_seconds, images, window_seconds=30):
    """タイムスタンプの前後の画像を取得"""
    if not images:
        return []
    
    matching_images = []
    for image in images:
        filepath, start_time, end_time = image
        # タイムスタンプの前後window_seconds秒以内の画像を含める
        if (start_time - window_seconds <= timestamp_seconds <= end_time + window_seconds):
            matching_images.append(filepath)
    
    return matching_images[:6]  # 最大6枚まで表示

def txt_to_html(lines, output_html_path, urlbase="", images=None):
    html_lines = [
        '<html>',
        '<head><meta charset="utf-8">',
        '<style>',
        'body { font-family: sans-serif; line-height: 1.7em; padding: 1em; background: #f9f9f9; }',
        'h1, h2, h3, h4 { color: #2c3e50; border-bottom: 1px solid #ccc; padding-bottom: 0.3em; margin-top: 1.5em; }',
        'ul { margin-left: 1.5em; }',
        'li { margin-bottom: 0.3em; }',
        'p { margin-top: 0.8em; }',
        'a { color: #2980b9; text-decoration: none; }',
        '.timestamp-section { margin: 1em 0; }',
        '.timestamp-images { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; margin-bottom: 1em; }',
        '.timestamp-image { width: 100%; height: 120px; object-fit: contain; background: #eee; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }',
        '.timestamp-content { width: 100%; }',
        '</style>',
        '</head>',
        '<body>'
    ]

    in_list = False
    for line in lines:
        line = line.strip()
        if not line:
            continue

        match = re.search(r"(\d+)分(\d+)秒頃", line)
        timestamp_html = ""
        matching_image = None
        
        if match:
            total_seconds = int(match.group(1)) * 60 + int(match.group(2))
            jump_url = f"{urlbase}{total_seconds}"
            timestamp_html = f'<p><a href="{jump_url}" target="_blank">▶ 動画リンク</a></p>'
            line = re.sub(r"\*\*(\d+分\d+秒頃)\*\*", r"\1", line)
            
            # タイムスタンプに対応する画像を探す
            if images:
                image_paths = find_matching_images(total_seconds, images)
                if image_paths:
                    matching_image = '<div class="timestamp-images">'
                    for path in image_paths:
                        # 相対パスに変換
                        rel_path = os.path.relpath(
                            path,
                            os.path.dirname(output_html_path)
                        ).replace('\\', '/')
                        matching_image += f'<img src="{rel_path}" class="timestamp-image" alt="Screenshot at {match.group(1)}:{match.group(2)}">'
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
            line = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", line)
            content_html += f"<li>{line[1:].strip()}</li>"
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
