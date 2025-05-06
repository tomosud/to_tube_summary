import re
import os
import pyperclip
import sys
import requests
#import subprocess
from youtube_transcript_api import YouTubeTranscriptApi
from ret_youyaku_html import do as create_summary

import yt_dlp
from PIL import Image
import io

import html
import unicodedata

BASE_DIR = r"C:\temp\html"

def create_output_dirs(title):
    """出力用のディレクトリを作成"""
    # ファイル名をフォルダ名として使用
    output_dir = os.path.join(BASE_DIR, title)
    images_dir = os.path.join(output_dir, "images")
    
    # ディレクトリを作成
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)
    
    return output_dir, images_dir

def download_and_slice_image(url, video_id, start_time, duration, cols, rows, fragment_idx, base_cell_size):
    """画像をダウンロードしてスライスする"""
    try:
        # 画像をダウンロード
        response = requests.get(url)
        if response.status_code != 200:
            print(f"⚠️ 画像のダウンロードに失敗: {response.status_code}")
            return []

        # 画像をPILで開く
        img = Image.open(io.BytesIO(response.content))
        
        # デバッグ用に元画像を保存
        original_filename = f"{video_id}_original_{fragment_idx}.jpg"
        original_filepath = os.path.join(images_dir, original_filename)
        img.save(original_filepath, "JPEG")
        print(f"✅ 元画像を保存: {original_filename}")
        
        # 実際の画像サイズを取得
        actual_width, actual_height = img.size
        print(f"実際の画像サイズ: {actual_width}x{actual_height}")
        
        # 基準のセルサイズを使用
        cell_width, cell_height = base_cell_size
        print(f"基準セルサイズ: {cell_width}x{cell_height}, 分割: {cols}x{rows}")
        
        # 1セルあたりの時間を計算（デュレーションを総セル数で割る）
        cells_count = cols * rows
        time_per_cell = duration / cells_count
        
        sliced_images = []
        
        # 画像をグリッドに従ってスライス
        for row in range(rows):
            for col in range(cols):
                # 画像の切り出し範囲を計算
                left = col * cell_width
                top = row * cell_height
                right = left + cell_width
                bottom = top + cell_height
                
                # セル画像を切り出して保存
                cell = img.crop((left, top, right, bottom))
                print(f"セルサイズ: {cell.size[0]}x{cell.size[1]}")
                
                # グリッドポジションからタイムスタンプを計算
                cell_index = row * cols + col
                cell_start_time = start_time + (cell_index * time_per_cell)
                cell_end_time = cell_start_time + time_per_cell
                
                # 時間を文字列に変換（HHMMSS形式）
                start_time_str = format_time_vtt(cell_start_time).replace(":", "").replace(".", "")
                end_time_str = format_time_vtt(cell_end_time).replace(":", "").replace(".", "")
                
                # ファイル名を生成（Windows対応のタイムスタンプ形式）
                filename = f"{video_id}_t{start_time_str}_to_{end_time_str}_f{fragment_idx}.jpg"
                filepath = os.path.join(images_dir, filename)
                
                # 画像を保存
                cell.save(filepath, "JPEG")
                sliced_images.append((filepath, cell_start_time, cell_end_time))
        
        return sliced_images
    except Exception as e:
        print(f"⚠️ 画像処理エラー: {str(e)}")
        return []

def dl_images(url, images_dir):
    """
    ストーリーボード画像をダウンロードしてスライス
    
    各フラグメントの画像は以下のように処理されます：
    1. 元画像を保存（デバッグ用）
    2. 実際の画像サイズを取得して動的にスライス
    3. グリッドに従って画像を分割
    4. 各スライスに正確なタイムスタンプを付与
    
    Returns:
        list[tuple]: [(filepath, start_time, end_time), ...]
    """
    
    with yt_dlp.YoutubeDL({'skip_download': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        video_id = info['id']

    # ストーリーボード形式を取得
    sb1_format = next((f for f in info.get("formats", []) 
                    if f.get("format_note") == "storyboard" and f.get("format_id") == "sb0"), None)

    if sb1_format:
        print("✅ ストーリーボード情報:")
        print(f"画像サイズ: {sb1_format['width']}x{sb1_format['height']}")
        print(f"分割: {sb1_format['columns']}列 × {sb1_format['rows']}行")
        print(f"フラグメント数: {len(sb1_format['fragments'])}")
        
        # 最初のフラグメントから基準となるセルサイズを計算
        try:
            # 最初のフラグメントの画像を取得
            first_response = requests.get(sb1_format['fragments'][0]['url'])
            if first_response.status_code == 200:
                first_img = Image.open(io.BytesIO(first_response.content))
                base_width = first_img.size[0] // sb1_format['columns']
                base_height = first_img.size[1] // sb1_format['rows']
                base_cell_size = (base_width, base_height)
                print(f"基準セルサイズを設定: {base_width}x{base_height}")
            else:
                raise Exception("最初のフラグメントの取得に失敗しました")
        except Exception as e:
            print(f"⚠️ 基準セルサイズの計算エラー: {str(e)}")
            return []
        
        all_images = []
        current_time = 0
        
        # 各フラグメントを処理
        for idx, fragment in enumerate(sb1_format['fragments']):
            print(f"フラグメント {idx + 1}/{len(sb1_format['fragments'])} を処理中...")
            
            # 画像をダウンロードしてスライス
            images = download_and_slice_image(
                fragment['url'],
                video_id,
                current_time,
                fragment['duration'],
                sb1_format['columns'],
                sb1_format['rows'],
                idx,
                base_cell_size
            )
            
            all_images.extend(images)
            current_time += fragment['duration']
        
        print(f"✅ 合計 {len(all_images)} 枚の画像を保存しました")
        return all_images
    else:
        print("⚠️ ストーリーボード形式が見つかりませんでした")
        return []

def sanitize_filename(title):
    """タイトルをファイル名やURLの一部に安全に使えるように変換"""
    if not title:
        return ""
    
    print(f"元のタイトル: {title}")

    # HTMLエンティティをデコード
    title = html.unescape(title)

    # Unicodeの制御文字などを除去（ゼロ幅スペースなど）
    title = ''.join(ch for ch in title if unicodedata.category(ch)[0] != 'C')

    # ファイル名やURLで使えない/紛らわしい文字を除去
    title = re.sub(r'[\\/*?:"<>|&=%#@!`~^\[\]{}();\'\",。、「」‘’“”].', "", title)

    # 半角スペースや全角スペースをアンダースコアに
    title = re.sub(r'\s+', '_', title)

    # 連続するアンダースコアは1つにまとめる
    title = re.sub(r'_+', '_', title)

    # 前後のアンダースコアを削除
    title = title.strip('_')

    title = title.replace(".", "")

    # 長すぎるタイトルは切り詰める（パス長制限やURL長対策）
    if len(title) > 100:
        title = title[:97] + "..."

    print(f"加工後のタイトル: {title}")

    return title
'''
def sanitize_filename(title):
    """ファイル名に使用できない文字を除去"""
    if not title:
        return ""
    print (f"元のタイトル: {title}")
    # HTMLエンティティをデコード
    title = title.replace("&quot;", "")
    title = title.replace("&amp;", "and")
    title = title.replace("&lt;", "")
    title = title.replace("&gt;", "")

    title = title.replace("&#39;", " ")
  
    # ファイル名に使用できない文字を除去
    title = re.sub(r'[\\/*?:"<>|!%&=\'].;:', "", title)
    
    # スペースをアンダースコアに置換
    title = title.replace(" ", "_")
    
    # 長すぎるタイトルを切り詰める（Windowsのパス長制限対策）
    if len(title) > 100:
        title = title[:97] + "..."
        
    return title
'''
def get_video_id(url):
    """URLから動画IDを抽出"""
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_youtube_title(video_id):
    """YouTubeの動画タイトルをWebページから取得"""
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        response = requests.get(url)
        if response.status_code == 200:
            # タイトルを抽出（<title>タグの内容を取得）
            title_match = re.search(r'<title>(.*?)</title>', response.text)
            if title_match:
                title = title_match.group(1)
                # YouTubeのタイトルには " - YouTube" が付くので削除
                title = title.replace(" - YouTube", "")
                return title
    except Exception as e:
        print(f"タイトル取得エラー: {str(e)}")
    return None

def download_transcript(video_id, output_dir):
    try:
        # 出力ディレクトリ作成
        os.makedirs(output_dir, exist_ok=True)
        
        # 動画のタイトルをWebページから取得
        print("動画タイトルを取得中...")
        video_title = get_youtube_title(video_id)
        if video_title:
            original_title = video_title
            video_title = sanitize_filename(video_title)
            print(f"動画タイトル: {original_title}")
            print(f"ファイル名: {video_title}")
        else:
            video_title = video_id
            print("タイトルを取得できませんでした。動画IDを使用します。")
        
        print("利用可能な字幕を確認中...")
        # 利用可能な字幕のリストを取得
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # 字幕の優先順位: 日本語 > 英語 > その他
        transcript = None
        transcript_language = None
        
        # 日本語字幕を試す
        try:
            transcript = transcript_list.find_transcript(['ja']).fetch()
            transcript_language = '日本語'
            print("日本語字幕が見つかりました")
        except Exception as e:
            print("日本語字幕は見つかりませんでした、英語字幕を試します...")
            
            # 英語字幕を試す（en, en-US）
            try:
                try:
                    transcript = transcript_list.find_transcript(['en']).fetch()
                    transcript_language = '英語'
                except:
                    transcript = transcript_list.find_transcript(['en-US']).fetch()
                    transcript_language = '英語（US）'
                print(f"{transcript_language}字幕が見つかりました")
            except Exception as e:
                print("\n--利用可能な字幕言語:")
                tcode = None

                for t in transcript_list:
                    print(f"- {t.language} ({t.language_code})")

                    tcode = t.language_code
                #raise Exception("日本語・英語の字幕が見つかりませんでした。")

                    transcript = transcript_list.find_transcript([tcode]).fetch()   
                    print(f"{tcode}字幕が見つかりました")
                # その他の言語字幕を試す（日本語・英語が見つからなかった場合）

        
        # VTT形式に変換
        print("VTT形式に変換中...")
        vtt_content = "WEBVTT\n\n"
        for i, entry in enumerate(transcript, 1):
            # FetchedTranscriptSnippetオブジェクトから直接属性にアクセス
            start_time = entry.start
            duration = entry.duration
            end_time = start_time + duration
            
            # 時間をVTT形式に変換 (HH:MM:SS.mmm)
            start_str = format_time_vtt(start_time)
            end_str = format_time_vtt(end_time)
            
            text = entry.text
            
            # VTTエントリを追加
            vtt_content += f"{start_str} --> {end_str}\n{text}\n\n"
        
        # ファイル名を動画タイトルから生成
        if not video_title:
            # タイトルが取得できなかった場合は動画IDを使用
            output_file = os.path.join(output_dir, f"{video_id}.vtt")
        else:
            output_file = os.path.join(output_dir, f"{video_title}.vtt")
        
        # ファイル保存
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(vtt_content)
        
        return output_file
        
    except Exception as e:
        print(f"エラーが発生しました: {str(e)}")
        return None

def format_time(seconds):
    """秒数をSRT形式の時間文字列に変換 (HH:MM:SS,mmm)"""
    hours = int(seconds / 3600)
    minutes = int((seconds % 3600) / 60)
    seconds = seconds % 60
    milliseconds = int((seconds - int(seconds)) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"

def format_time_vtt(seconds):
    """秒数をVTT形式の時間文字列に変換 (HH:MM:SS.mmm)"""
    hours = int(seconds / 3600)
    minutes = int((seconds % 3600) / 60)
    seconds = seconds % 60
    milliseconds = int((seconds - int(seconds)) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{int(seconds):02d}.{milliseconds:03d}"

def is_running_from_bat():
    """batファイルから実行されているかどうかを判定"""
    return "--from-bat" in sys.argv

if __name__ == "__main__":
    print("=== YouTube字幕ダウンローダー (Transcript API版) ===")
    try:
        # 実行方法に応じてURLを取得
        if not is_running_from_bat():
            # pyファイルから直接実行した場合はデバッグ用URLを使用
            url = "https://www.youtube.com/watch?v=fXdp-K882aE"
            print(f"デバッグモード: {url}")
        else:
            # batファイルから実行した場合はクリップボードからURL取得
            try:
                url = pyperclip.paste().strip()
                if not url.startswith("http"):
                    url = input("YouTube動画のURLを入力してください: ").strip()
            except:
                url = input("YouTube動画のURLを入力してください: ").strip()
        
        
        video_id = get_video_id(url)
        
        if not video_id:
            print("有効なYouTube URLではありません")
            input("Enterキーを押して終了...")
            sys.exit(1)
            

        # タイトルを取得してディレクトリを作成
        video_title = get_youtube_title(video_id)
        if not video_title:
            video_title = video_id
        safe_title = sanitize_filename(video_title)
        
        # 出力ディレクトリを作成
        output_dir, images_dir = create_output_dirs(safe_title)
        
        # 字幕を処理
        result = download_transcript(video_id, output_dir)
        
        if result:
            print(f"字幕が保存されました: {result}")

            # 要約処理の実行
            print("\n要約処理を開始します...")
            try:
                
                video_url = f"https://www.youtube.com/watch?v={video_id}&t="
                
                # 画像をダウンロードしてスライス（1回のみ実行）
                print("\nストーリーボード画像の処理を開始...")
                images = dl_images(url, images_dir)
                html_path = create_summary(result, video_title, output_dir, video_url, images)
                print(f"要約HTMLが作成されました: {html_path}")
                
                # VTTファイルを削除
                #os.remove(result)
                print("VTTファイルを削除しました")
                
                # HTMLをブラウザで開く
                os.startfile(html_path)
                print("ブラウザでHTMLを開きました")
            except Exception as e:
                print(f"要約処理でエラーが発生しました: {str(e)}")
        else:
            print("字幕の取得に失敗しました")
            
    except Exception as e:
        print(f"予期せぬエラー: {str(e)}")
    finally:
        #input("Enterキーを押して終了...")
        sys.exit(0)
