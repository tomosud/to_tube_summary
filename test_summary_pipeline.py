import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch


os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import ret_youyaku_html as summary_module  # noqa: E402
from ret_youyaku_html import (  # noqa: E402
    _allocate_quotas,
    _clean_model_markdown,
    chapters_to_section_bounds,
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


def _blocks(count, step=10):
    return [(i, i * step, f"text{i}") for i in range(count)]


class ChaptersToSectionBoundsTest(unittest.TestCase):
    def test_snaps_to_nearest_block_start(self):
        bounds = chapters_to_section_bounds(
            _blocks(30), [(0, "A"), (43, "B"), (152, "C")], 300
        )
        self.assertEqual(bounds, [(0, "A", 0), (40, "B", 4), (150, "C", 15)])

    def test_adds_intro_when_first_chapter_starts_late(self):
        bounds = chapters_to_section_bounds(
            _blocks(30), [(60, "A"), (120, "B"), (200, "C")], 300
        )
        self.assertEqual(bounds[0], (0, "導入", 0))
        self.assertEqual([b[1] for b in bounds], ["導入", "A", "B", "C"])

    def test_removes_duplicates_after_snapping(self):
        bounds = chapters_to_section_bounds(
            _blocks(30), [(0, "A"), (41, "B"), (44, "B2"), (100, "C")], 300
        )
        self.assertEqual([b[1] for b in bounds], ["A", "B", "C"])
        self.assertEqual([b[2] for b in bounds], sorted({b[2] for b in bounds}))

    def test_merges_down_to_forty_sections(self):
        chapters = [(i * 10, f"C{i}") for i in range(60)]
        bounds = chapters_to_section_bounds(_blocks(60), chapters, 600)
        self.assertEqual(len(bounds), 40)
        self.assertEqual(bounds[0][0], 0)
        starts = [b[0] for b in bounds]
        self.assertEqual(starts, sorted(set(starts)))


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
        response = SimpleNamespace(parsed_output=parsed)
        fake_client = SimpleNamespace(
            messages=SimpleNamespace(parse=lambda **_kwargs: response)
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


class ContactSheetTest(unittest.TestCase):
    def _imgs(self, n, size=(320, 180)):
        from PIL import Image
        return [Image.new("RGB", size, (i * 20 % 255, 100, 150)) for i in range(n)]

    def test_grid_dimensions_and_rows(self):
        import io
        from PIL import Image
        data, rows = summary_module._build_contact_sheet(self._imgs(10))
        self.assertEqual(rows, 3)
        sheet = Image.open(io.BytesIO(data))
        self.assertEqual(sheet.format, "JPEG")
        self.assertEqual(sheet.size, (4 * 240, 3 * 135))

    def test_fewer_candidates_than_columns(self):
        import io
        from PIL import Image
        data, rows = summary_module._build_contact_sheet(self._imgs(2))
        self.assertEqual(rows, 1)
        self.assertEqual(Image.open(io.BytesIO(data)).size, (2 * 240, 135))

    def test_oversized_sheet_is_scaled_down(self):
        import io
        from PIL import Image
        # 縦長画像24枚: 6行 x 427px = 2562px > 1568px
        data, rows = summary_module._build_contact_sheet(self._imgs(24, size=(180, 320)))
        self.assertEqual(rows, 6)
        sheet = Image.open(io.BytesIO(data))
        self.assertLessEqual(max(sheet.size), 1568)
        self.assertGreaterEqual(max(sheet.size), 1566)

    def test_accepts_path_tuples_and_tolerates_unreadable(self):
        import io
        import tempfile
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            good = os.path.join(d, "a.jpg")
            self._imgs(1)[0].save(good)
            data, rows = summary_module._build_contact_sheet(
                [(good, 0, 1), (os.path.join(d, "missing.jpg"), 1, 2)]
            )
        self.assertEqual(rows, 1)
        self.assertEqual(Image.open(io.BytesIO(data)).size[0], 2 * 240)


if __name__ == "__main__":
    unittest.main()
