import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch


os.environ.setdefault("OPENAI_API_KEY", "test-key")

import ret_youyaku_html as summary_module  # noqa: E402
from ret_youyaku_html import (  # noqa: E402
    _allocate_quotas,
    _clean_model_markdown,
    extract_timestamp,
    markdown_to_html,
    parse_description_chapters,
)


class DescriptionChapterTest(unittest.TestCase):
    def test_parses_minute_and_hour_chapters(self):
        description = """Chapters:
00:00 Intro
02:29 Installation
1:02:03 Long conclusion
not a chapter
"""
        self.assertEqual(
            parse_description_chapters(description, video_duration_sec=4000),
            [(0, "Intro"), (149, "Installation"), (3723, "Long conclusion")],
        )

    def test_ignores_duplicates_and_out_of_range_entries(self):
        description = "00:10 First\n00:10 Duplicate\n99:99 Invalid\n20:00 Too late"
        self.assertEqual(
            parse_description_chapters(description, video_duration_sec=300),
            [(10, "First")],
        )


class SummaryHelperTest(unittest.TestCase):
    def test_quota_allocation_preserves_total(self):
        quotas = _allocate_quotas(7, [10, 10])
        self.assertEqual(sum(quotas), 7)
        self.assertTrue(all(value >= 1 for value in quotas))

    def test_clean_model_markdown_removes_only_trailing_closer(self):
        self.assertEqual(
            _clean_model_markdown("本文中では以上の条件を使う。\n\n以上"),
            "本文中では以上の条件を使う。",
        )

    def test_extract_timestamp_supports_hours(self):
        self.assertEqual(extract_timestamp("（動画：1時間2分3秒頃）"), 3723)

    def test_markdown_escapes_raw_html(self):
        rendered = markdown_to_html("<script>alert(1)</script>\n**safe**")
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("<b>safe</b>", rendered)


class Stage3Test(unittest.TestCase):
    def test_merge_updates_heading_for_combined_content(self):
        parsed = summary_module._PolishResult(
            sections=[
                summary_module._PolishedSection(
                    heading="最初の話題", merge_with_previous=False
                ),
                summary_module._PolishedSection(
                    heading="二つの内容を表す統合見出し", merge_with_previous=True
                ),
            ],
            highlights="特徴的なポイント",
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))]
        )
        fake_client = SimpleNamespace(
            beta=SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(parse=lambda **_kwargs: response)
                )
            )
        )
        outline = summary_module._OutlineResult(sections=[
            summary_module._Section(heading="A", start_seconds=0),
            summary_module._Section(heading="B", start_seconds=60),
        ])
        summaries = [
            summary_module._SectionSummary(heading="A", summary="本文A"),
            summary_module._SectionSummary(heading="B", summary="本文B"),
        ]

        with patch.object(summary_module, "client", fake_client), patch.object(
            summary_module, "count_tokens", return_value=(0, 0)
        ):
            merged_outline, merged_summaries, highlights = summary_module.stage3_polish(
                outline, summaries, "動画"
            )

        self.assertEqual(len(merged_outline.sections), 1)
        self.assertEqual(merged_outline.sections[0].heading, "二つの内容を表す統合見出し")
        self.assertEqual(merged_summaries[0].heading, "二つの内容を表す統合見出し")
        self.assertEqual(merged_summaries[0].summary, "本文A\n\n本文B")
        self.assertEqual(highlights, "特徴的なポイント")


if __name__ == "__main__":
    unittest.main()
