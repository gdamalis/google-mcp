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
