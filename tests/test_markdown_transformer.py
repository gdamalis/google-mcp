"""Unit tests for tools/docs/_markdown.py."""

import pytest

from tools.docs._markdown import markdown_to_requests


class TestHeadings:
    def test_h1(self):
        reqs = markdown_to_requests("# Hello", insert_index=1)
        # Expect: insertText "Hello\n" at 1, then updateParagraphStyle to HEADING_1
        text_reqs = [r for r in reqs if "insertText" in r]
        style_reqs = [r for r in reqs if "updateParagraphStyle" in r]

        assert len(text_reqs) == 1
        assert text_reqs[0]["insertText"]["text"] == "Hello\n"
        assert text_reqs[0]["insertText"]["location"]["index"] == 1

        assert len(style_reqs) == 1
        assert style_reqs[0]["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"] == "HEADING_1"
        assert style_reqs[0]["updateParagraphStyle"]["range"]["startIndex"] == 1
        assert style_reqs[0]["updateParagraphStyle"]["range"]["endIndex"] == 7  # len("Hello\n") + 1

    def test_h2_through_h6(self):
        for level in range(2, 7):
            md = "#" * level + " Title"
            reqs = markdown_to_requests(md, insert_index=1)
            style_reqs = [r for r in reqs if "updateParagraphStyle" in r]
            assert style_reqs[0]["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"] == f"HEADING_{level}"

    def test_two_headings_in_a_row(self):
        reqs = markdown_to_requests("# One\n\n## Two", insert_index=1)
        text_reqs = [r for r in reqs if "insertText" in r]
        assert len(text_reqs) == 2
        # cursor advances: "One\n" = 4 chars + 1 base = idx 5 for "Two\n"
        assert text_reqs[1]["insertText"]["location"]["index"] == 5


class TestParagraphsAndInline:
    def test_plain_paragraph(self):
        reqs = markdown_to_requests("Hello world.", insert_index=1)
        text_reqs = [r for r in reqs if "insertText" in r]
        assert len(text_reqs) == 1
        assert text_reqs[0]["insertText"]["text"] == "Hello world.\n"

    def test_bold(self):
        reqs = markdown_to_requests("Hello **bold** text.", insert_index=1)
        text_reqs = [r for r in reqs if "insertText" in r]
        # Single insertText (entire paragraph)
        assert text_reqs[0]["insertText"]["text"] == "Hello bold text.\n"
        # One text-style request for the bold range
        style_reqs = [r for r in reqs if "updateTextStyle" in r]
        bold_style = [s for s in style_reqs if s["updateTextStyle"]["textStyle"].get("bold")]
        assert len(bold_style) == 1
        # "Hello " = 6 chars, so "bold" range is 7..11 (1-based)
        rng = bold_style[0]["updateTextStyle"]["range"]
        assert rng["startIndex"] == 7
        assert rng["endIndex"] == 11

    def test_italic(self):
        reqs = markdown_to_requests("*hi*", insert_index=1)
        ts = [r for r in reqs if "updateTextStyle" in r and r["updateTextStyle"]["textStyle"].get("italic")]
        assert len(ts) == 1

    def test_strikethrough(self):
        reqs = markdown_to_requests("~~gone~~", insert_index=1)
        ts = [r for r in reqs if "updateTextStyle" in r and r["updateTextStyle"]["textStyle"].get("strikethrough")]
        assert len(ts) == 1

    def test_inline_code(self):
        reqs = markdown_to_requests("use `print()`", insert_index=1)
        ts = [r for r in reqs if "updateTextStyle" in r]
        mono = [r for r in ts if r["updateTextStyle"]["textStyle"].get("weightedFontFamily", {}).get("fontFamily") == "Roboto Mono"]
        assert len(mono) == 1

    def test_link(self):
        reqs = markdown_to_requests("[click](https://example.com)", insert_index=1)
        ts = [r for r in reqs if "updateTextStyle" in r]
        links = [r for r in ts if r["updateTextStyle"]["textStyle"].get("link", {}).get("url") == "https://example.com"]
        assert len(links) == 1


class TestLists:
    def test_unordered_list(self):
        md = "- one\n- two\n- three"
        reqs = markdown_to_requests(md, insert_index=1)
        text_reqs = [r for r in reqs if "insertText" in r]
        contents = "".join(r["insertText"]["text"] for r in text_reqs)
        assert "one" in contents and "two" in contents and "three" in contents

        # One createParagraphBullets request covering the whole list range
        bullet_reqs = [r for r in reqs if "createParagraphBullets" in r]
        assert len(bullet_reqs) == 1
        assert bullet_reqs[0]["createParagraphBullets"]["bulletPreset"] == "BULLET_DISC_CIRCLE_SQUARE"

    def test_ordered_list(self):
        reqs = markdown_to_requests("1. one\n2. two", insert_index=1)
        bullet_reqs = [r for r in reqs if "createParagraphBullets" in r]
        assert bullet_reqs[0]["createParagraphBullets"]["bulletPreset"] == "NUMBERED_DECIMAL_ALPHA_ROMAN"

    def test_checkbox_list(self):
        reqs = markdown_to_requests("- [ ] todo\n- [x] done", insert_index=1)
        bullet_reqs = [r for r in reqs if "createParagraphBullets" in r]
        assert bullet_reqs[0]["createParagraphBullets"]["bulletPreset"] == "BULLET_CHECKBOX"

    def test_nested_list(self):
        md = "- one\n  - one-a\n  - one-b\n- two"
        reqs = markdown_to_requests(md, insert_index=1)
        text_reqs = [r for r in reqs if "insertText" in r]
        # Nested items get \t prefix per Docs API convention
        contents = "".join(r["insertText"]["text"] for r in text_reqs)
        assert "\tone-a\n" in contents
        assert "\tone-b\n" in contents


class TestBlocks:
    def test_fenced_code(self):
        md = "```python\nprint('hi')\n```"
        reqs = markdown_to_requests(md, insert_index=1)
        text_reqs = [r for r in reqs if "insertText" in r]
        contents = "".join(r["insertText"]["text"] for r in text_reqs)
        assert "print('hi')" in contents

        # Should apply Roboto Mono + background shading
        text_styles = [r for r in reqs if "updateTextStyle" in r]
        mono = [s for s in text_styles
                if s["updateTextStyle"]["textStyle"].get("weightedFontFamily", {}).get("fontFamily") == "Roboto Mono"]
        assert len(mono) >= 1

        para_styles = [r for r in reqs if "updateParagraphStyle" in r]
        shaded = [s for s in para_styles
                  if s["updateParagraphStyle"]["paragraphStyle"].get("shading", {}).get("backgroundColor")]
        assert len(shaded) >= 1

    def test_blockquote(self):
        reqs = markdown_to_requests("> quote me", insert_index=1)
        para_styles = [r for r in reqs if "updateParagraphStyle" in r]
        indented = [s for s in para_styles
                    if s["updateParagraphStyle"]["paragraphStyle"].get("indentStart", {}).get("magnitude", 0) > 0]
        assert len(indented) >= 1

    def test_horizontal_rule(self):
        reqs = markdown_to_requests("---", insert_index=1)
        para_styles = [r for r in reqs if "updateParagraphStyle" in r]
        with_border = [s for s in para_styles
                       if s["updateParagraphStyle"]["paragraphStyle"].get("borderBottom")]
        assert len(with_border) >= 1


class TestImages:
    def test_image_url_inline(self):
        md = "![alt](https://example.com/img.png)"
        reqs = markdown_to_requests(md, insert_index=1)
        img_reqs = [r for r in reqs if "insertInlineImage" in r]
        assert len(img_reqs) == 1
        assert img_reqs[0]["insertInlineImage"]["uri"] == "https://example.com/img.png"
        assert img_reqs[0]["insertInlineImage"]["location"]["index"] == 1

    def test_image_local_path_skipped_in_pure_transformer(self):
        """Local paths require Drive upload — not in scope for the pure transformer.
        They're handled by the public insert_image tool. The transformer should
        either skip or emit a placeholder request the caller can post-process."""
        md = "![alt](./local.png)"
        reqs = markdown_to_requests(md, insert_index=1)
        img_reqs = [r for r in reqs if "insertInlineImage" in r]
        # Local paths cannot be inserted via Docs API directly — skip with a log.
        assert len(img_reqs) == 0


class TestTables:
    def test_table_emits_insert_table(self):
        md = "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
        reqs = markdown_to_requests(md, insert_index=1)
        # Expect one insertTable request with rows=3 (header + 2 body), columns=2
        table_reqs = [r for r in reqs if "insertTable" in r]
        assert len(table_reqs) == 1
        assert table_reqs[0]["insertTable"]["rows"] == 3
        assert table_reqs[0]["insertTable"]["columns"] == 2

    def test_table_cell_data_in_pending(self):
        """Cell text is collected as 'pending_cell_inserts' on the result list — it's
        a sentinel dict with no top-level Docs API key, processed by
        render_markdown_to_doc after a re-read."""
        md = "| a | b |\n|---|---|\n| 1 | 2 |"
        reqs = markdown_to_requests(md, insert_index=1)
        pending = [r for r in reqs if r.get("_pending_table")]
        assert len(pending) == 1
        cells = pending[0]["_pending_table"]["cells"]
        # 2 rows × 2 cols = 4 cells, row-major: a, b, 1, 2
        assert [c["text"] for c in cells] == ["a", "b", "1", "2"]
        assert pending[0]["_pending_table"]["header_row"] == 0
