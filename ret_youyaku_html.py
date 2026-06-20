import os
import re
import json
import shutil
import glob
import hashlib
import urllib.parse
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from pydantic import BaseModel
from typing import List
import tkinter as tk
from tkinter import simpledialog


# ── Structured Outputs 用 Pydantic モデル ──────────────────────────────────

class _Section(BaseModel):
    heading: str        # セクション見出し（日本語、20字以内）
    start_seconds: int  # そのセクションが始まる秒数

class _OutlineResult(BaseModel):
    sections: List[_Section]

class _SectionSummary(BaseModel):
    heading: str  # 結論を含む一行要約の見出し（20〜40字）
    summary: str  # Markdown本文（見出し行なし）

# Pass 1（窓ごとの切り分け）の出力。境界は秒数ではなくブロックIDで返させる。
class _BlockSection(BaseModel):
    start_block_id: int  # そのセクションが始まる字幕ブロックのID
    heading: str         # 仮見出し（日本語20字以内）

class _WindowOutline(BaseModel):
    sections: List[_BlockSection]

# Pass 3（全体整合）の出力。入力セクションと1対1・同順で返させる。
class _PolishedSection(BaseModel):
    heading: str               # 全体を俯瞰して整えた見出し（20〜40字）
    merge_with_previous: bool  # 直前セクションと実質同じ話題なら true（統合）

class _PolishResult(BaseModel):
    sections: List[_PolishedSection]

# テンプレートファイルのパス
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template')
TEMPLATE_HTML = os.path.join(TEMPLATE_DIR, 'index.html')

def get_api_key():
    """APIキーを取得または設定する（DPAPI暗号化）"""
    import win32crypt
    api_key_file = "localsettings.bin"

    # 暗号化ファイルが存在する場合は復号して返す
    if os.path.exists(api_key_file):
        with open(api_key_file, "rb") as f:
            encrypted = f.read()
        _, decrypted = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)
        return decrypted.decode("utf-8").strip()

    # ファイルが存在しない場合はダイアログを表示して入力を求める
    root = tk.Tk()
    root.withdraw()  # メインウィンドウを非表示

    api_key = simpledialog.askstring(
        "API Key 設定",
        "OpenAI APIキーを入力してください：\n（入力されたキーはapi_key.binに暗号化して保存されます）"
    )

    if api_key:
        # APIキーをWindowsユーザーに紐付けて暗号化して保存
        encrypted = win32crypt.CryptProtectData(
            api_key.strip().encode("utf-8"), None, None, None, None, 0
        )
        with open(api_key_file, "wb") as f:
            f.write(encrypted)
        return api_key.strip()
    else:
        raise ValueError("APIキーが設定されていません。")

# APIキーを設定
apikey = get_api_key()
print('---apikey set!')

# OpenAIクライアントを初期化
client = OpenAI(api_key=apikey)

# 使用するモデル（環境変数から取得、デフォルトはgpt-5.2）
MODEL_NAME = os.environ.get('OPENAI_MODEL', 'gpt-5.2-2025-12-11')
# Stage 1（分散指示）/ Stage 2（heading指示）で別モデルを使用可能
MODEL_STAGE1 = os.environ.get('OPENAI_MODEL_STAGE1', MODEL_NAME)
MODEL_STAGE2 = os.environ.get('OPENAI_MODEL_STAGE2', MODEL_NAME)

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


# ── 2段階要約 ヘルパー関数群 ───────────────────────────────────────────────

def _seconds_to_label(sec: int) -> str:
    """秒数を「X分Y秒」形式に変換（judge_good_time_split の format_time と同様）"""
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}時間{m}分{s}秒"
    return f"{m}分{s}秒"


def _dedup_join(texts) -> str:
    """字幕の連続テキスト断片を、重複・部分重なりを除去して連結する。

    build_section_text のマージロジックと同じ（マーカー処理なし版）。
    """
    merged = []
    for text in texts:
        if merged and text == merged[-1]:
            continue
        if merged:
            prev = merged[-1]
            max_overlap = min(len(prev), len(text), 50)
            overlap_found = False
            for overlap_len in range(max_overlap, 2, -1):
                if prev.endswith(text[:overlap_len]):
                    merged[-1] = prev + text[overlap_len:]
                    overlap_found = True
                    break
            if overlap_found:
                continue
        merged.append(text)
    return ' '.join(merged)


def build_blocks(vtt_entries, target_block_sec: float = 10.0):
    """vtt_entries を ~target_block_sec ごとのブロックに束ねて返す。

    各ブロックは字幕の実タイムスタンプを保持するため、ブロックIDから
    正確な開始秒を逆引きできる（LLMに秒数を推測させないための土台）。

    Returns:
        list of tuples: [(block_id, start_seconds, text), ...]
    """
    blocks = []
    cur_start = None
    cur_texts = []

    def flush():
        nonlocal cur_start, cur_texts
        if cur_start is None:
            return
        text = _dedup_join(cur_texts)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text).strip()
        if text:
            blocks.append((len(blocks), cur_start, text))
        cur_start = None
        cur_texts = []

    for entry_start, _entry_end, text in vtt_entries:
        if cur_start is not None and entry_start - cur_start >= target_block_sec:
            flush()
        if cur_start is None:
            cur_start = entry_start
        cur_texts.append(text)
    flush()
    return blocks


def _render_blocks(blocks, lo: int, hi: int) -> str:
    """blocks[lo:hi] を「[id] (M:SS) テキスト」形式の文字列にする。

    (M:SS) はモデルが話題の長さ・配分を把握するための参考表示で、
    境界の確定にはブロックIDのみを使う。
    """
    lines = []
    for bid, start_sec, text in blocks[lo:hi]:
        m, s = divmod(int(start_sec), 60)
        lines.append(f"[{bid}] ({m:d}:{s:02d}) {text}")
    return "\n".join(lines)


def build_section_text(vtt_entries, start_sec: int, end_sec: int, timestamps: bool = True) -> str:
    """指定時間範囲の字幕テキストを抽出して返す。

    timestamps=True のとき約60秒ごとに [MM:SS] マーカーを挿入する（Stage 1用）。
    timestamps=False のときテキストのみ返す（Stage 2用）。
    """
    texts = []
    last_marker_sec = -999

    for entry_start, _entry_end, text in vtt_entries:
        if entry_start < start_sec:
            continue
        if entry_start >= end_sec:
            break

        if timestamps and entry_start - last_marker_sec >= 60:
            m, s = divmod(int(entry_start), 60)
            texts.append(f"[{m:02d}:{s:02d}]")
            last_marker_sec = entry_start

        texts.append(text)

    # 重複除去（get_subtitle_for_range と同じロジック）
    merged = []
    for text in texts:
        if text.startswith('[') and text.endswith(']'):
            merged.append(text)
            continue
        if merged and text == merged[-1]:
            continue
        if merged and not (merged[-1].startswith('[') and merged[-1].endswith(']')):
            prev = merged[-1]
            max_overlap = min(len(prev), len(text), 50)
            overlap_found = False
            for overlap_len in range(max_overlap, 2, -1):
                if prev.endswith(text[:overlap_len]):
                    merged[-1] = prev + text[overlap_len:]
                    overlap_found = True
                    break
            if overlap_found:
                continue
        merged.append(text)

    result = ' '.join(merged)
    # JSON シリアライズを壊す制御文字を除去（null バイト・改行以外の制御文字）
    result = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', result)
    return result


def _validate_outline(outline: _OutlineResult, video_duration_sec: int) -> bool:
    """Stage 1 のアウトラインが適切な分散を持つか検証する"""
    if len(outline.sections) < 3:
        return False
    starts = [s.start_seconds for s in outline.sections]
    if starts != sorted(starts):
        return False
    if len(starts) != len(set(starts)):
        return False
    if video_duration_sec > 0 and (starts[-1] / video_duration_sec) < 0.5:
        return False
    return True


def stage1_get_outline(vtt_entries, title: str, video_duration_sec: int, description: str = None) -> _OutlineResult:
    """Stage 1: VTT全体からセクションのアウトライン（見出し＋開始秒数）を取得する。

    LLMの long-context 特性（中盤の注意が薄れ、分割が前半に偏る）を避けるため、
    字幕を時間でほぼ等分した「窓」に分け、各窓へ時間比例のセクション数ノルマを
    与えて並列に切り分ける（map方式）。境界は秒数ではなくブロックIDで返させ、
    ブロックの実タイムスタンプへ逆引きするので、推測による誤差が入らない。
    """
    blocks = build_blocks(vtt_entries)
    n_blocks = len(blocks)
    if n_blocks == 0:
        raise ValueError("Stage 1: 字幕ブロックが空です。")

    block_start = {bid: start_sec for bid, start_sec, _t in blocks}

    duration_min = max(video_duration_sec // 60, 1)
    # 目標セクション総数（おおむね2分に1個、5〜20の範囲）
    target_total = min(max(round(duration_min / 2), 5), 20)
    target_total = min(target_total, n_blocks)

    # 窓数: 1窓あたり約5セクション。窓を小さく保つことで各ブロックが必ず
    # どこかの窓の「フォーカス内」に入り、中盤の見落とし・前半偏重を防ぐ。
    n_windows = max(1, math.ceil(target_total / 5))
    n_windows = min(n_windows, n_blocks)

    # ブロックを n_windows 個の連続レンジへ等分（ブロック数ベース＝ほぼ時間等分）
    bounds = [round(i * n_blocks / n_windows) for i in range(n_windows + 1)]

    system_prompt = (
        "あなたは動画字幕の構造分析スペシャリストです。"
        "渡された区間だけを読み、話題の切れ目を正確に識別します。"
    )
    desc_block = (
        f"\n【動画のDescription（参考情報）】\n{description}\n"
        if description else ""
    )

    def segment_window(win_idx):
        lo, hi = bounds[win_idx], bounds[win_idx + 1]
        # 窓のノルマ＝総数をブロック数で時間比例配分（最低1）
        quota = max(1, round(target_total * (hi - lo) / n_blocks))
        first_id, last_id = blocks[lo][0], blocks[hi - 1][0]
        block_text = _render_blocks(blocks, lo, hi)
        user_prompt = (
            f"以下は動画「{title}」字幕の一部（全{n_windows}区間中の第{win_idx+1}区間）です。\n"
            f"各行は「[ブロックID] (時刻) テキスト」の形式です。\n"
            f"この区間を話題の切れ目で {quota} 個のセクションに分割してください。\n"
            f"{desc_block}\n"
            f"【ルール】\n"
            f"- セクションはちょうど {quota} 個にしてください。\n"
            f"- start_block_id には、その話題が始まる行の【ブロックID】を指定してください"
            f"（この区間内 {first_id}〜{last_id} のいずれか）。秒数ではなくブロックIDです。\n"
            f"- 最初のセクションの start_block_id は必ず {first_id} にしてください。\n"
            f"- start_block_id は昇順で、重複させないでください。\n"
            f"- heading は日本語で、その話題を端的に表す20字以内にしてください。\n"
            f"\n字幕（ブロックID付き）:\n{block_text}"
        )
        response = client.beta.chat.completions.parse(
            model=MODEL_STAGE1,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=_WindowOutline,
        )
        count_tokens(response)
        return win_idx, lo, hi, response.choices[0].message.parsed

    results = [None] * n_windows
    if n_windows == 1:
        results[0] = segment_window(0)
    else:
        with ThreadPoolExecutor(max_workers=min(5, n_windows)) as executor:
            futures = {executor.submit(segment_window, i): i for i in range(n_windows)}
            for future in as_completed(futures):
                i = futures[future]
                try:
                    results[i] = future.result()
                except Exception as e:
                    print(f"  [Stage 1] 第{i+1}区間でエラー: {e} → 再試行中...")
                    results[i] = segment_window(i)

    # 窓の結果を時系列に結合（ブロックIDで重複排除し、実秒へ変換）
    merged = {}  # block_id -> heading（先勝ち）
    for win_idx, lo, hi, win_outline in sorted(results, key=lambda r: r[0]):
        lo_id, hi_id = blocks[lo][0], blocks[hi - 1][0]
        for s in win_outline.sections:
            bid = max(lo_id, min(hi_id, s.start_block_id))  # 区間内へクランプ
            merged.setdefault(bid, (s.heading or "").strip() or "（無題）")

    # 先頭は必ずブロック0始まりにする
    first_bid = blocks[0][0]
    if first_bid not in merged:
        merged[first_bid] = next(iter(merged.values())) if merged else "導入"

    sections = [
        _Section(heading=merged[bid], start_seconds=int(block_start[bid]))
        for bid in sorted(merged)
    ]
    outline = _OutlineResult(sections=sections)
    print(f"  [Stage 1] {n_windows}区間から{len(sections)}セクションを検出")
    return outline


def stage2_summarize_section(section: _Section, section_text: str,
                              outline: _OutlineResult, title: str, idx: int, description: str = None) -> _SectionSummary:
    """Stage 2: 1セクション分の字幕テキストを要約して _SectionSummary を返す"""
    n = len(outline.sections)
    outline_list = "\n".join(
        f"{i+1}. {s.heading}（{_seconds_to_label(s.start_seconds)}〜）"
        for i, s in enumerate(outline.sections)
    )

    end_sec = (outline.sections[idx + 1].start_seconds
               if idx + 1 < n else None)
    start_label = _seconds_to_label(section.start_seconds)
    end_label = _seconds_to_label(end_sec) if end_sec else "動画終端"

    system_prompt = (
        "あなたは動画字幕のセクション要約スペシャリストです。\n"
        "指定されたセクションの字幕を、内容を損なわず読みやすく要約します。\n"
        "前のセクションで紹介された用語は再定義不要です。\n"
        "文体は常体（だ・ます調ではなく）で書いてください。\n"
        "ただし「〜である」を機械的に文末に付けないでください。\n"
        "「〜する」「〜している」「〜なる」「〜だ」など、自然な常体の語尾を使い分けてください。"
    )

    desc_block = (
        f"\n【動画のDescription（参考情報）】\n{description}\n"
        if description else ""
    )
    user_prompt = (
        f"動画「{title}」の要約を作成しています。\n"
        f"以下は動画全体のアウトライン（全{n}セクション）です：\n\n"
        f"{outline_list}\n"
        f"{desc_block}\n"
        f"今回はセクション{idx+1}「{section.heading}」（{start_label}〜{end_label}）を要約してください。\n\n"
        f"【headingのルール】\n"
        f"- 「何についての話か」＋「その結論・評価」を20〜40字の一文で表してください。\n"
        f"- 商品・人物・技術の紹介や評価が中心の内容では、対象の名前や種別を先に示し、続けて結論・評価を書いてください。\n"
        f"  例：「○○（商品名）は旨味はあるが塩気が強くそのままではしょっぱめ」\n"
        f"- 議論・解説・手順など対象が明確でない場合は、何が明らかになったかを結論として書いてください。\n"
        f"- 単なるトピックラベル（「○○の紹介」「○○について」）にはしないでください。\n\n"
        f"【summaryのルール】\n"
        f"- このセクションの字幕テキストのみを扱ってください。他のセクションの内容は含めないでください。\n"
        f"- 要約ではなくリライトとして扱ってください。元の意味・結論・温度感を保ちながら、重複・言い換え・枝葉の説明を整理して引き締めてください。\n"
        f"  字数を削ることを目的にせず、冗長をなくすことで自然に締まった文章にしてください。\n"
        f"- まず1文で、このセクションの最も重要な結論・事実を直接述べてください。\n"
        f"  「本セクションでは〜が説明された」のようなメタ記述は避け、内容を直接書いてください。\n"
        f"- 話題ごとに段落を分け、必要に応じて各段落の冒頭に短い小見出しを付けてください。\n"
        f"  小見出しは `####` 形式で書いてください（例：`#### 音楽の評価`）。\n"
        f"  小見出しを閉じるための単独の `####` 行は出力しないでください。\n"
        f"  小見出しは分類名ではなく、その段落の要点が分かる表現にしてください。\n"
        f"  小見出しだけ追っても、大まかな流れが分かるようにしてください。\n"
        f"- 原則として本文は自然な文章で整えてください。\n"
        f"  事実の列挙・比較・条件・注意点など、箇条書きのほうが明らかに読みやすい場合に限って使ってよいですが、前後の文脈が切れないようにしてください。\n"
        f"- 1文を長くしすぎず、必要に応じて分割してください。関連する内容は同じ段落にまとめ、意味のないところで改行しないこと。\n"
        f"- 具体例や補足が複数ある場合は代表例だけ残してよいですが、主張の根拠が失われないようにしてください。\n"
        f"- 元のテキストの重要な論拠・専門用語を保持してください。\n"
        f"- 見出し行は不要です（呼び出し元が付けます）。\n"
        f"- Markdown形式で出力してください。\n\n"
        f"セクションの字幕テキスト:\n{section_text}"
    )

    response = client.beta.chat.completions.parse(
        model=MODEL_STAGE2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format=_SectionSummary,
    )
    count_tokens(response)
    return response.choices[0].message.parsed


def stage2_summarize_all_parallel(vtt_entries, outline: _OutlineResult, title: str, description: str = None) -> list:
    """Stage 2: 全セクションを ThreadPoolExecutor で並列要約する。

    戻り値: セクション順に並んだ要約文字列のリスト
    """
    sections = outline.sections
    n = len(sections)
    results = [None] * n

    def task(idx):
        sec = sections[idx]
        end_sec = sections[idx + 1].start_seconds if idx + 1 < n else float('inf')
        section_text = build_section_text(vtt_entries, sec.start_seconds, end_sec, timestamps=False)
        summary = stage2_summarize_section(sec, section_text, outline, title, idx, description=description)
        return idx, summary

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(task, i): i for i in range(n)}
        for future in as_completed(futures):
            try:
                idx, summary = future.result()
                results[idx] = summary
                print(f"  [Stage 2] セクション {idx+1}/{n} 完了")
            except Exception as e:
                idx = futures[future]
                print(f"  [Stage 2] セクション {idx+1}/{n} でエラー: {e} → リトライ中...")
                try:
                    _, results[idx] = task(idx)
                    print(f"  [Stage 2] セクション {idx+1}/{n} リトライ成功")
                except Exception as e2:
                    print(f"  [Stage 2] セクション {idx+1}/{n} リトライ失敗: {e2}")
                    results[idx] = _SectionSummary(
                        heading=sections[idx].heading,
                        summary="（このセクションの要約を生成できませんでした）"
                    )

    return results


def stage3_polish(outline: _OutlineResult, summaries: list, title: str):
    """Pass 3: 全セクションの見出し＋本文を一度に俯瞰し、見出しを横断的に整え、
    実質同じ話題の隣接セクションを統合する。

    並列のStage 2では原理的に不可能な「全体を見た上での」整合をここで行う。
    本文は再生成せず（情報欠落・出力コスト増を避ける）、見出しと統合フラグのみを
    LLMに返させる。失敗・不整合時は入力をそのまま返す（安全側フォールバック）。

    戻り値: (新しい _OutlineResult, 新しい summaries[_SectionSummary])
    """
    n = len(outline.sections)
    if n == 0:
        return outline, summaries

    def heading_of(sec, res):
        return res.heading if isinstance(res, _SectionSummary) else sec.heading

    def body_of(res):
        return res.summary if isinstance(res, _SectionSummary) else (res or "")

    headings = [heading_of(sec, res) for sec, res in zip(outline.sections, summaries)]
    bodies = [body_of(res) for res in summaries]

    listing = "\n\n".join(
        f"{i+1}.\n見出し: {headings[i]}\n本文: {bodies[i]}"
        for i in range(n)
    )
    system_prompt = (
        "あなたは動画要約の編集者です。全セクションを俯瞰し、見出しを統一感のある"
        "形に整え、実質同じ話題の隣接セクションを統合判断します。"
    )
    user_prompt = (
        f"以下は動画「{title}」の全{n}セクションの見出しと本文です。\n"
        f"全体を俯瞰して、各セクションの見出しを整えてください。\n\n"
        f"【目的】\n"
        f"- 各見出しは「対象＋結論・評価」を含む20〜40字の一文にし、語調と粒度をそろえる。\n"
        f"- 見出しだけを上から読めば動画全体の流れが分かるようにする。\n"
        f"- 直前のセクションと実質同じ話題（分割しすぎ）なら merge_with_previous=true にする。\n\n"
        f"【制約】\n"
        f"- 入力と同じ数（{n}個）・同じ順番で sections を返してください。"
        f"統合する場合も枠は残し、merge_with_previous=true で示してください。\n"
        f"- 先頭セクションの merge_with_previous は必ず false にしてください。\n"
        f"- 本文は返さなくて構いません（見出しと統合フラグのみ）。\n\n"
        f"セクション一覧:\n{listing}"
    )
    try:
        response = client.beta.chat.completions.parse(
            model=MODEL_STAGE1,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=_PolishResult,
        )
        count_tokens(response)
        polished = response.choices[0].message.parsed.sections
    except Exception as e:
        print(f"  [Stage 3] 整合に失敗（元の見出しを使用）: {e}")
        return outline, summaries

    if len(polished) != n:
        print(f"  [Stage 3] 返却数が不一致（{len(polished)}≠{n}）→ 元の見出しを使用")
        return outline, summaries

    new_sections = []
    new_summaries = []
    for i in range(n):
        new_heading = (polished[i].heading or "").strip() or headings[i]
        merge = polished[i].merge_with_previous and i > 0 and bool(new_summaries)
        if merge:
            # 直前セクションへ本文を連結（見出し・開始秒は直前を維持）
            prev = new_summaries[-1]
            prev.summary = (prev.summary.rstrip() + "\n\n" + bodies[i]).strip()
        else:
            new_sections.append(_Section(
                heading=new_heading,
                start_seconds=outline.sections[i].start_seconds,
            ))
            new_summaries.append(_SectionSummary(heading=new_heading, summary=bodies[i]))

    merged_count = n - len(new_sections)
    print(f"  [Stage 3] 見出しを整え、{merged_count}セクションを統合")
    return _OutlineResult(sections=new_sections), new_summaries


def assemble_markdown(outline: _OutlineResult, summaries: list, title: str) -> str:
    """アウトラインとセクション要約から最終 Markdown を組み立てる。

    見出しは Stage 2 が生成した結論を含む一行要約を使用する。
    txt_to_html() が期待する形式:
      ## タイトル
      ### 見出し（動画：X分Y秒頃）
      本文
      以上
    """
    lines = [f"## {title}", ""]
    for sec, result in zip(outline.sections, summaries):
        label = _seconds_to_label(sec.start_seconds)
        heading = result.heading if isinstance(result, _SectionSummary) else sec.heading
        body = result.summary if isinstance(result, _SectionSummary) else (result or "")
        lines.append(f"### {heading}（動画：{label}頃）")
        lines.append(body)
        lines.append("")
    lines.append("以上")
    return "\n".join(lines)


def yoyaku_gemini(vtt, title, output_html_path, images=None, detail_text=None, thumbnail_path=None, images_future=None, description=None):
    """字幕ファイルを要約してHTMLを生成する（3パス方式）

    images_future: concurrent.futures.Future を渡すと、HTML生成直前に
                   images_future.result() → (images, thumbnail_path) として解決する。
                   ストーリーボードダウンロードと要約を並列実行するために使用。
    """
    result_merged_txt = read_vtt(vtt)
    vtt_entries = parse_vtt_with_timestamps(result_merged_txt)
    video_duration_sec = get_vtt_duration_in_seconds(result_merged_txt)

    print(f'要約中（Stage1: {MODEL_STAGE1} / Stage2: {MODEL_STAGE2}）')

    # ── タイトル和訳（英語タイトルに日本語訳を付加）────────────────────────
    print('  [Title] 和訳確認中...')
    display_title = make_display_title(title)
    if display_title != title:
        print(f'  [Title] {display_title}')

    # ── Stage 1: アウトライン取得（AIプロンプトには原題を使用）────────────
    print('  [Stage 1] アウトライン生成中...')
    outline = stage1_get_outline(vtt_entries, title, video_duration_sec, description=description)

    # ── Stage 2: セクション並列要約 ────────────────────────────────────────
    print(f'  [Stage 2] {len(outline.sections)}セクションを並列要約中...')
    summaries = stage2_summarize_all_parallel(vtt_entries, outline, title, description=description)

    # ── Stage 3: 全体整合（見出しの統一・分割しすぎの統合）──────────────────
    print('  [Stage 3] 全体整合中...')
    outline, summaries = stage3_polish(outline, summaries, display_title)

    # ── Markdown 組み立て（表示用タイトルを使用）──────────────────────────
    responseA_text = assemble_markdown(outline, summaries, display_title)

    # ── ハイライト生成 ─────────────────────────────────────────────────────
    print('  [Highlights] ポイント生成中...')
    highlights_messages = [
        {"role": "user", "content": f"以下は動画「{title}」の要約です。\n\n{responseA_text}"},
        {"role": "assistant", "content": "要約を確認しました。"},
        {
            "role": "user",
            "content": "では、その内容の興味深いポイントをまとめて。200文字程度で日本語で。「動画のポイント」という見出しを付けて。この講演に興味を持つ人が特記したいような内容を。全般的でなくとも、特徴的な点を。またこっちは文末に「以上」は不要。"
        },
    ]

    responseB = client.chat.completions.create(
        model=MODEL_NAME,
        messages=highlights_messages
    )

    in_tok, out_tok = count_tokens(responseB)
    print(f"  ポイント: 入力 {in_tok:,} / 出力 {out_tok:,} トークン")

    responseB_text = responseB.choices[0].message.content

    result = responseB_text.split('\n') + ['\n'] + [url_base] + responseA_text.split('\n')

    # ストーリーボードの並列ダウンロードが完了するまで待機
    if images_future is not None:
        print('  [Images] ストーリーボードの完了を待機中...')
        images, thumbnail_path = images_future.result()

    # HTMLファイルを生成
    txt_to_html(result, output_html_path, url_base, images, detail_text, thumbnail_path, vtt_entries, display_title, description=description)

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
        "h1,h2{color:#ff9800;border-bottom:1px solid #333;padding-bottom:.3em;margin-top:1.5em}",
        "h3,h4{color:#ffb74d;font-size:0.95em;margin-top:1.2em;margin-bottom:0.2em}",
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
        ".ai-summary-link{margin-left:1em;color:#4fc3f7;font-size:0.85em;padding:2px 8px;background:#2a2a2a;border-radius:4px}",
        ".ai-summary-link:hover{background:#3a3a3a;color:#fff}",
        "</style>",
        "</head>",
        "<body>"
    ]

def markdown_to_html(text):
    """MarkdownテキストをHTMLに変換する"""
    text = text.replace('\\r\\n', '\n').replace('\\n', '\n')
    text = re.sub(r'(?<!^)(?<!\n)(#{1,6}\s+\S)', r'\n\1', text)
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

def txt_to_html(lines, output_html_path, urlbase: str = "", images=None, detail_text=None, thumbnail_path=None, vtt_entries=None, title: str = "", description: str = None):
    """Markdown ライクなテキストを data.js + index.html に変換

    従来のモノリシックHTML生成の代わりに:
    - data.js: 動画固有のデータ（セクション、画像パス、字幕テキスト等）
    - index.html: 汎用テンプレート（template/index.htmlのコピー）
    を出力する。プロキシURL等の加工はテンプレート側で行う。
    """

    output_dir = os.path.dirname(output_html_path)

    def normalize_markdown_lines(source):
        if isinstance(source, str):
            source = source.splitlines()

        normalized = []
        for raw in source:
            text = str(raw).replace('\r\n', '\n').replace('\r', '\n')
            # Structured model output sometimes contains literal "\n#### ..."
            # inside a paragraph. Split it before heading detection.
            text = text.replace('\\r\\n', '\n').replace('\\n', '\n')
            text = re.sub(r'(?<!^)(?<!\n)(#{1,6}\s+\S)', r'\n\1', text)
            normalized.extend(text.split('\n'))
        return normalized

    lines = normalize_markdown_lines(lines)

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

    def build_image_data(match_list):
        """画像マッチ結果を data.js 用の辞書リストに変換"""
        result = []
        for path, img_start, img_end in match_list:
            rel = os.path.relpath(path, output_dir).replace('\\', '/')
            result.append({"src": rel, "start": img_start, "end": img_end})
        return result

    def parse_markdown_heading(line: str):
        """Markdown の ATX 見出しを解析する。

        AI が `#### 見出し ####` や区切りだけの `####` を返すことがあるため、
        見出し本文とマーカーだけの行を明確に分けて扱う。
        """
        m = re.match(r'^\s*(#{1,6})(.*)$', line)
        if not m:
            return None
        level = min(len(m.group(1)), 4)
        heading_text = m.group(2).strip()
        heading_text = re.sub(r'\s+#{1,6}\s*$', '', heading_text).strip()
        return level, heading_text

    def inline_markdown_to_html(text: str):
        replaced = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        return re.sub(r"\*\*", "", replaced)

    # ---------------------- urlbase から video_id を抽出 ---------------------- #
    video_id_match = re.search(r'[?&]v=([a-zA-Z0-9_-]+)', urlbase)
    video_id = video_id_match.group(1) if video_id_match else ''

    # ---------------------- サムネイルの相対パス ---------------------- #
    thumbnail_rel = None
    if thumbnail_path and os.path.exists(thumbnail_path):
        thumbnail_rel = os.path.relpath(thumbnail_path, output_dir).replace('\\', '/')

    # ---------------------- 全タイムスタンプを収集 ---------------------- #
    timestamps = [(idx, parse_timestamp(raw)) for idx, raw in enumerate(lines) if parse_timestamp(raw) is not None]

    # ---------------------- セクションバッファ ---------------------- #
    sections = []
    current = {"heading": "", "heading_text": "", "level": 2, "body": [], "images": [], "timestamp": None, "subtitle": None}

    def flush():
        nonlocal current
        if not current["heading_text"] and not current["body"]:
            return
        sections.append({
            "heading": current["heading_text"],
            "level": current["level"],
            "body": "\n".join(current["body"]) if current["body"] else "",
            "images": current["images"],
            "timestamp": current["timestamp"],
            "subtitle": current["subtitle"],
        })
        current = {"heading": "", "heading_text": "", "level": 2, "body": [], "images": [], "timestamp": None, "subtitle": None}

    in_list = False

    def add_timestamp_data(ts_sec, idx):
        """タイムスタンプに関連する画像と字幕をcurrentに設定"""
        next_sec = next((sec for i2, sec in timestamps if i2 > idx), None)
        if images:
            imgs = find_matching_images(ts_sec, next_sec, images)
            if imgs:
                current["images"] = build_image_data(imgs)
        current["timestamp"] = ts_sec
        if vtt_entries:
            subtitle_text = get_subtitle_for_range(vtt_entries, ts_sec, next_sec)
            if subtitle_text:
                current["subtitle"] = subtitle_text

    # ---------------------- メインループ ---------------------- #
    for idx, raw in enumerate(lines):
        line = raw.rstrip()
        if not line:
            continue

        # ----- 見出し ----- #
        heading = parse_markdown_heading(line)
        if heading:
            if in_list:
                current["body"].append("</ul>")
                in_list = False

            level, heading_text = heading
            if not heading_text:
                continue

            ts_sec = parse_timestamp(heading_text)
            if level >= 4 and ts_sec is None:
                current["body"].append(f"<h{level}>{inline_markdown_to_html(heading_text)}</h{level}>")
                continue

            flush()
            current["heading_text"] = heading_text
            current["level"] = level
            if ts_sec is not None:
                add_timestamp_data(ts_sec, idx)
            continue

        # ----- タイムスタンプ単独行 ----- #
        ts_sec_inline = parse_timestamp(line)
        ts_only_line = bool(re.fullmatch(r"(?:動画[:：]?\s*)?(?:[0-9]+時間)?(?:[0-9]+分)?[0-9]+秒頃", line))
        if ts_only_line and ts_sec_inline is not None:
            add_timestamp_data(ts_sec_inline, idx)
            continue

        # ----- リスト項目内のタイムスタンプ付き項目を見出し化 ----- #
        list_item_match = re.match(
            r'^[\s*\-0-9.]+\*\*([^*]+（動画[:：]?\s*(?:[0-9]+時間)?(?:[0-9]+分)?[0-9]+秒頃）)\*\*(?:[:：]?\s*(.*))?$',
            line
        )
        if list_item_match:
            if in_list:
                current["body"].append("</ul>")
                in_list = False
            flush()
            heading_text = list_item_match.group(1).strip()
            body_text = list_item_match.group(2).strip() if list_item_match.group(2) else None

            current["heading_text"] = heading_text
            current["level"] = 4

            ts_sec = parse_timestamp(heading_text)
            if ts_sec is not None:
                add_timestamp_data(ts_sec, idx)

            if body_text:
                current["body"].append(f"<p>{inline_markdown_to_html(body_text)}</p>")
            continue

        # ----- 本文 / リスト ----- #
        if line.lstrip().startswith("*"):
            if not in_list:
                current["body"].append("<ul>")
                in_list = True
            item_raw = line.lstrip("* ")
            if re.fullmatch(r"\*\*\s*\*\*", item_raw.strip()):
                continue
            current["body"].append(f"<li>{inline_markdown_to_html(item_raw)}</li>")
        else:
            if in_list:
                current["body"].append("</ul>")
                in_list = False
            if line.startswith("http://") or line.startswith("https://"):
                current["body"].append(f'<p><a href="{line}" target="_blank">{line}</a></p>')
            else:
                current["body"].append(f"<p>{inline_markdown_to_html(line)}</p>")

    if in_list:
        current["body"].append("</ul>")
    flush()

    # ---------------------- PAGE_DATA を構築 ---------------------- #
    page_data = {
        "schema_version": 1,
        "title": title,
        "video_id": video_id,
        "url": urlbase,
        "thumbnail": thumbnail_rel,
        "sections": sections,
        "detail": markdown_to_html(detail_text) if detail_text else None,
        "description": description or None,
    }

    # ---------------------- data.js を書き出し ---------------------- #
    data_js_path = os.path.join(output_dir, 'data.js')
    with open(data_js_path, "w", encoding="utf-8") as fp:
        fp.write("var PAGE_DATA = ")
        json.dump(page_data, fp, ensure_ascii=False, indent=2)
        fp.write(";\n")
    print(f"✅ data.js 作成: {data_js_path}")

    # ---------------------- テンプレート index.html をコピー ---------------------- #
    index_html_path = os.path.join(output_dir, 'index.html')
    shutil.copy2(TEMPLATE_HTML, index_html_path)
    print(f"✅ index.html コピー: {index_html_path}")

    # ---------------------- テキスト保存（従来互換） ---------------------- #
    with open(os.path.join(output_dir, 'index.html.txt'), "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines))
    print(f"✅ テキスト保存: index.html.txt")


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

def make_display_title(title: str) -> str:
    """タイトルが日本語以外の場合、原題の後ろに和訳を付けて返す。
    日本語が主体の場合はそのまま返す。"""
    if not title:
        return title
    prompt = (
        f"以下の動画タイトルを確認してください。\n"
        f"日本語以外（英語など）で書かれている場合は、自然な日本語訳だけを出力してください。\n"
        f"日本語が主体の場合は何も出力しないでください（空文字）。\n"
        f"タイトルの訳のみを出力し、説明・記号・引用符は不要です。\n\n"
        f"{title}"
    )
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}]
        )
        count_tokens(response)
        ja = response.choices[0].message.content.strip()
        if ja:
            return f"{title}　{ja}"
    except Exception as e:
        print(f"⚠️ タイトル和訳エラー: {str(e)}")
    return title

def filter_description(description: str, title: str) -> str:
    """descriptionから要約補足に使えそうな部分を抜粋して返す。日本語以外は和訳。失敗時はNone。"""
    if not description:
        return None
    prompt = (
        f"以下のdescriptionから、動画字幕の要約に補足として使えそうな箇所だけを抜粋してください。\n\n"
        f"【言語について】\n"
        f"- descriptionが日本語で書かれている場合は、原文のまま一字一句変えずに抜粋してください。\n"
        f"- 日本語以外の言語で書かれている場合は、抜粋する箇所を日本語に訳して出力してください。\n"
        f"  訳す際も要約・言い換えはせず、原文の意味を忠実に日本語にしてください。\n\n"
        f"【共通条件】\n"
        f"- 要約しない\n"
        f"- 言い換えしない\n"
        f"- 箇条書きに再構成しない\n"
        f"- 情報を分類しない\n"
        f"- 原文にない見出しを足さない\n"
        f"- 順番は原文どおり\n"
        f"- 不要な箇所は省略してよい\n"
        f"- 広告、関連動画、チャンネル登録、共有、視聴回数、ハッシュタグ、画像出典は除外\n"
        f"- 時間を含む見出し（例：00:23 【兵士】甘煮）は重要なので残す\n"
        f"- 動画のなかで紹介してるものの情報やURLも残す\n"
        f"- 出力は抜粋・訳出した内容だけにする\n\n"
        f"動画タイトル：{title}\n\n"
        f"Description:\n{description}"
    )
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}]
        )
        count_tokens(response)
        result = response.choices[0].message.content.strip()
        return result or None
    except Exception as e:
        print(f"⚠️ description フィルタエラー: {str(e)}")
        return None

def do(vtt_path, video_title, output_dir, url=None, images=None, detail_mode=False, thumbnail_path=None, images_future=None, description=None):
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
        str: 生成されたHTMLファイルのパス（index.html）
    """
    # パスの正規化
    vtt = vtt_path.replace('\\','/')
    title = video_title
    
    # HTMLファイルのパスを設定（index.html に統一）
    html_path = os.path.join(output_dir, 'index.html')
    
    # URLをグローバル変数に設定（要約時に使用）
    # 注: プロキシURL変換はテンプレート側で行うため、正規URLのまま保持
    global url_base
    if url:
        url_base = url
    
    # 詳細テキストを生成（詳細モードの場合のみ）
    detail_text = None
    if detail_mode:
        print('\n詳細テキストを生成中...')
        vtt_content = read_vtt(vtt)
        detail_text = generate_detail_text(vtt_content, title)
    
    yoyaku_gemini(vtt, title, html_path, images, detail_text, thumbnail_path, images_future=images_future, description=description)

    # トークン使用量サマリーを表示
    print_token_summary()

    # 出力フォルダ全体のテンプレートを自動更新
    base_dir = os.path.dirname(output_dir)
    update_templates(base_dir)

    return html_path


# ====================== テンプレート自動更新 ====================== #

def _file_hash(path):
    """ファイルのSHA256ハッシュを返す。存在しなければNone。"""
    try:
        with open(path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def update_templates(base_dir):
    """base_dir 以下の全フォルダの index.html テンプレートを最新版に更新する。
    data.js が存在するフォルダのみ対象（新フォーマット済み）。
    テンプレートの内容ハッシュで比較するため、バージョン番号の管理は不要。
    """
    if not os.path.isdir(base_dir):
        return

    template_hash = _file_hash(TEMPLATE_HTML)
    if template_hash is None:
        return

    updated = 0
    for folder_name in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder_name)
        if not os.path.isdir(folder_path):
            continue
        data_js = os.path.join(folder_path, 'data.js')
        index_html = os.path.join(folder_path, 'index.html')
        if not os.path.exists(data_js):
            continue  # 旧フォーマット or 無関係フォルダ → スキップ
        if _file_hash(index_html) != template_hash:
            shutil.copy2(TEMPLATE_HTML, index_html)
            updated += 1

    if updated:
        print(f"🔄 テンプレート更新: {updated} フォルダの index.html を更新しました")


# ====================== 既存データ移行 ====================== #

def migrate_legacy_html(base_dir):
    """base_dir 以下の旧フォーマット（モノリシックHTML）フォルダを
    data.js + index.html 形式に変換する。

    対象: data.js が存在せず、.html.txt（生テキスト）が存在するフォルダ
    """
    if not os.path.isdir(base_dir):
        print(f"⚠️ ディレクトリが存在しません: {base_dir}")
        return

    migrated = 0
    skipped = 0

    for folder_name in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder_name)
        if not os.path.isdir(folder_path):
            continue

        # 既に新フォーマットなら skip
        if os.path.exists(os.path.join(folder_path, 'data.js')):
            continue

        # .html.txt を探す
        txt_files = glob.glob(os.path.join(folder_path, '*.html.txt'))
        if not txt_files:
            continue

        txt_file = txt_files[0]
        print(f"\n--- 移行中: {folder_name} ---")

        try:
            # 1. 生テキスト読み込み
            with open(txt_file, 'r', encoding='utf-8') as f:
                raw_lines = f.read().split('\n')

            # 2. info.json から video_id, url を取得
            info_path = os.path.join(folder_path, 'info.json')
            video_id = ''
            url = ''
            if os.path.exists(info_path):
                with open(info_path, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                video_id = info.get('video_id', '')
                url = info.get('url', '')
            
            # URL が無い場合、video_id からURLを推定
            if not url and video_id:
                url = f"https://www.youtube.com/watch?v={video_id}&t="

            # 3. images/ から画像リストを構築
            images = []
            images_dir = os.path.join(folder_path, 'images')
            if os.path.isdir(images_dir):
                img_pattern = re.compile(r'_t(\d+)_to_(\d+)_')
                for img_file in os.listdir(images_dir):
                    if img_file.endswith('.jpg') and '_t' in img_file and '_to_' in img_file:
                        m = img_pattern.search(img_file)
                        if m:
                            # タイムスタンプ文字列をパース (HHMMSS000 形式)
                            start_str = m.group(1)
                            end_str = m.group(2)
                            start_sec = _parse_timestamp_str(start_str)
                            end_sec = _parse_timestamp_str(end_str)
                            if start_sec is not None and end_sec is not None:
                                filepath = os.path.join(images_dir, img_file)
                                images.append((filepath, start_sec, end_sec))
                images.sort(key=lambda x: x[1])

            # 4. VTTファイルから字幕データを取得
            vtt_entries = None
            vtt_files = glob.glob(os.path.join(folder_path, '*.vtt'))
            if vtt_files:
                vtt_content = read_vtt(vtt_files[0])
                vtt_entries = parse_vtt_with_timestamps(vtt_content)

            # 5. 旧HTMLから詳細セクションを取得（あれば）
            detail_text = _extract_detail_from_legacy_html(folder_path)

            # 6. data.js 生成（txt_to_html を呼ぶ）
            dummy_html_path = os.path.join(folder_path, 'index.html')
            txt_to_html(raw_lines, dummy_html_path, url, images or None, detail_text, 
                       os.path.join(folder_path, 'Thumbnail.jpg') if os.path.exists(os.path.join(folder_path, 'Thumbnail.jpg')) else None,
                       vtt_entries)

            # 7. 旧HTMLを .html.bak にリネーム
            for html_file in glob.glob(os.path.join(folder_path, '*.html')):
                basename = os.path.basename(html_file)
                if basename != 'index.html':
                    bak_path = html_file + '.bak'
                    os.rename(html_file, bak_path)
                    print(f"  旧HTML退避: {basename} → {basename}.bak")

            # 8. 旧 .html.txt を index.html.txt にリネーム（既にあれば不要）
            index_txt = os.path.join(folder_path, 'index.html.txt')
            if txt_file != index_txt and os.path.exists(txt_file):
                if not os.path.exists(index_txt):
                    shutil.copy2(txt_file, index_txt)

            migrated += 1
            print(f"  ✅ 移行完了")

        except Exception as e:
            print(f"  ⚠️ 移行失敗: {e}")
            skipped += 1

    print(f"\n=== 移行結果 ===")
    print(f"移行成功: {migrated} フォルダ")
    if skipped:
        print(f"移行失敗: {skipped} フォルダ")


def _parse_timestamp_str(ts_str):
    """画像ファイル名のタイムスタンプ文字列 (HHMMSSSSS = HH:MM:SS + mmm連結) を秒数に変換
    
    例: 000001966 → 00:00:01.966 → 1.966秒
        000130000 → 00:01:30.000 → 90秒
    """
    original = ts_str.zfill(9)  # 常に9桁にパディング
    h = int(original[0:2])
    m = int(original[2:4])
    s = int(original[4:6])
    ms = int(original[6:9])
    return h * 3600 + m * 60 + s + ms / 1000.0


def _extract_detail_from_legacy_html(folder_path):
    """旧HTMLから詳細セクションのテキストを抽出する（ベストエフォート）"""
    html_files = [f for f in glob.glob(os.path.join(folder_path, '*.html')) 
                  if os.path.basename(f) != 'index.html']
    if not html_files:
        return None
    
    try:
        with open(html_files[0], 'r', encoding='utf-8') as f:
            content = f.read()
        # <div id='detail-section'> ... </div> を探す
        m = re.search(r"<div id=['\"]detail-section['\"].*?>(.*?)</div>\s*(?:<script|</body>)", 
                      content, re.DOTALL)
        if m:
            detail_html = m.group(1)
            # <h2>📄 詳細内容</h2> を除去
            detail_html = re.sub(r'<h2>.*?詳細内容.*?</h2>', '', detail_html, count=1)
            return detail_html.strip() if detail_html.strip() else None
    except Exception:
        pass
    return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == '--migrate':
        # 移行モード: python ret_youyaku_html.py --migrate [base_dir]
        base = sys.argv[2] if len(sys.argv) >= 3 else r"C:\temp\html"
        migrate_legacy_html(base)
    elif len(sys.argv) >= 3:
        vtt_path = sys.argv[1]
        video_title = sys.argv[2]
        url = sys.argv[3] if len(sys.argv) > 3 else None
        do(vtt_path, video_title, url)
