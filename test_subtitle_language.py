import unittest

from subtitle_language import detect_video_language, matching_transcripts, ordered_transcripts


class FakeTranscript:
    def __init__(self, language_code, is_generated=False):
        self.language_code = language_code
        self.is_generated = is_generated


class SubtitleLanguageTest(unittest.TestCase):
    def test_metadata_language_has_priority(self):
        language, _ = detect_video_language(
            "日本語に翻訳されたタイトル", "en-US", []
        )
        self.assertEqual(language, "en")

    def test_generated_caption_identifies_source_language(self):
        tracks = [FakeTranscript("ja"), FakeTranscript("en", is_generated=True)]
        language, _ = detect_video_language("日本語タイトル", None, tracks)
        self.assertEqual(language, "en")

    def test_japanese_title(self):
        language, _ = detect_video_language("字幕を正しく選ぶ方法", None, [])
        self.assertEqual(language, "ja")

    def test_non_japanese_title_defaults_to_english(self):
        language, _ = detect_video_language("How captions work", None, [])
        self.assertEqual(language, "en")

    def test_matching_tracks_never_crosses_language(self):
        ja = FakeTranscript("ja")
        generated_en = FakeTranscript("en", is_generated=True)
        manual_en_gb = FakeTranscript("en-GB")
        matches = matching_transcripts([ja, generated_en, manual_en_gb], "en")
        self.assertEqual(matches, [manual_en_gb, generated_en])

    def test_ordered_transcripts_prefers_target_language(self):
        ja = FakeTranscript("ja")
        en = FakeTranscript("en")
        ordered = ordered_transcripts([en, ja], "ja")
        self.assertEqual(ordered, [ja, en])

    def test_ordered_transcripts_falls_back_to_english(self):
        # 英語動画と判定したが英語字幕がなく、日本語字幕しかない場合でも
        # 中止せず日本語字幕を候補として返す。
        ja = FakeTranscript("ja")
        ordered = ordered_transcripts([ja], "en")
        self.assertEqual(ordered, [ja])

    def test_ordered_transcripts_falls_back_to_any_available_language(self):
        # 判定言語が日本語で、英語字幕も無い場合は他の言語でも候補にする。
        fr = FakeTranscript("fr")
        ordered = ordered_transcripts([fr], "ja")
        self.assertEqual(ordered, [fr])

    def test_ordered_transcripts_manual_before_generated_across_fallback(self):
        target_generated = FakeTranscript("ja", is_generated=True)
        english_manual = FakeTranscript("en")
        ordered = ordered_transcripts([english_manual, target_generated], "ja")
        self.assertEqual(ordered, [target_generated, english_manual])

    def test_ordered_transcripts_empty_when_no_transcripts(self):
        self.assertEqual(ordered_transcripts([], "ja"), [])


if __name__ == "__main__":
    unittest.main()
