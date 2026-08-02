import re


_JAPANESE_KANA_RE = re.compile(r"[\u3040-\u30ff]")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def language_family(language_code):
    """言語コード・言語名を、このツールが扱う ja/en のどちらかへ正規化する。"""
    if not language_code:
        return None

    value = str(language_code).strip().lower().replace("_", "-")
    base = value.split("-", 1)[0]
    if base in {"ja", "jpn"} or value in {"japanese", "日本語"}:
        return "ja"
    if base in {"en", "eng"} or value in {"english", "英語"}:
        return "en"
    return None


def title_looks_japanese(title):
    """タイトルに仮名または漢字があれば日本語タイトルとみなす。"""
    if not title:
        return False
    return bool(_JAPANESE_KANA_RE.search(title) or _CJK_RE.search(title))


def detect_video_language(title, metadata_language=None, transcripts=()):
    """動画の原言語を ja/en のどちらかに判定し、判定理由も返す。

    自動生成字幕は通常、動画の音声から生成された原言語字幕なので、手動字幕より
    原言語の判定材料として優先する。判定不能時は英語に倒し、日本語への翻訳字幕を
    誤って選ぶ可能性を抑える。
    """
    metadata_family = language_family(metadata_language)
    if metadata_family:
        return metadata_family, "動画メタデータの言語"

    generated_languages = {
        language_family(getattr(track, "language_code", None))
        for track in transcripts
        if getattr(track, "is_generated", False)
    }
    generated_languages.discard(None)
    if len(generated_languages) == 1:
        return generated_languages.pop(), "自動生成字幕の言語"

    if title_looks_japanese(title):
        return "ja", "タイトルに日本語文字を検出"

    if title and title.strip():
        return "en", "タイトルに日本語文字がない"

    available_languages = {
        language_family(getattr(track, "language_code", None))
        for track in transcripts
    }
    available_languages.discard(None)
    if len(available_languages) == 1:
        return available_languages.pop(), "利用可能な字幕言語"

    return "en", "判定材料がないため安全側で英語"


def _transcripts_for_language(transcripts, language):
    candidates = [
        track for track in transcripts
        if language_family(getattr(track, "language_code", None)) == language
    ]
    return sorted(
        candidates,
        key=lambda track: (
            bool(getattr(track, "is_generated", False)),
            str(getattr(track, "language_code", "")).lower() != language,
        ),
    )


def matching_transcripts(transcripts, target_language):
    """対象言語の字幕を、手動・標準コード優先の順で返す。"""
    return _transcripts_for_language(transcripts, target_language)


def ordered_transcripts(transcripts, target_language):
    """取得を試みる字幕候補を優先順位順に並べる。

    判定言語の字幕を最優先とし、なければ英語、それも無ければ他の利用可能な
    言語の字幕を順に試す（各段階とも手動字幕を自動生成字幕より優先）。
    候補が1つもない場合のみ呼び出し側で要約を中止すればよく、判定言語と
    異なる字幕しかないという理由だけでは中止しない。
    """
    ordered = []
    seen_ids = set()

    def add(tracks):
        for track in tracks:
            if id(track) not in seen_ids:
                ordered.append(track)
                seen_ids.add(id(track))

    add(_transcripts_for_language(transcripts, target_language))
    if target_language != "en":
        add(_transcripts_for_language(transcripts, "en"))

    remaining = [track for track in transcripts if id(track) not in seen_ids]
    remaining.sort(key=lambda track: bool(getattr(track, "is_generated", False)))
    add(remaining)

    return ordered
