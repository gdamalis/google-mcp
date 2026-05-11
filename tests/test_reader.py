"""Unit tests for tools/docs/_reader.py."""

from tools.docs._reader import docs_to_markdown


def _doc_with(content):
    """Helper: wrap content in a minimal Docs JSON envelope."""
    return {"body": {"content": content}}


def _paragraph(text, *, named_style="NORMAL_TEXT", text_style=None):
    """Helper: build a paragraph element with one text run."""
    return {
        "paragraph": {
            "paragraphStyle": {"namedStyleType": named_style},
            "elements": [{
                "textRun": {
                    "content": text,
                    "textStyle": text_style or {},
                }
            }],
        }
    }


class TestReaderBasic:
    def test_empty_doc(self):
        assert docs_to_markdown(_doc_with([])) == ""

    def test_simple_paragraph(self):
        doc = _doc_with([_paragraph("Hello world.\n")])
        assert docs_to_markdown(doc).strip() == "Hello world."

    def test_heading_1(self):
        doc = _doc_with([_paragraph("Title\n", named_style="HEADING_1")])
        assert docs_to_markdown(doc).strip() == "# Title"

    def test_heading_2_through_6(self):
        for lvl in range(2, 7):
            doc = _doc_with([_paragraph("X\n", named_style=f"HEADING_{lvl}")])
            assert docs_to_markdown(doc).strip() == ("#" * lvl) + " X"

    def test_title_is_h1(self):
        doc = _doc_with([_paragraph("Doc\n", named_style="TITLE")])
        assert docs_to_markdown(doc).strip() == "# Doc"

    def test_bold(self):
        doc = _doc_with([{
            "paragraph": {
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                "elements": [
                    {"textRun": {"content": "Hi ", "textStyle": {}}},
                    {"textRun": {"content": "bold", "textStyle": {"bold": True}}},
                    {"textRun": {"content": " there\n", "textStyle": {}}},
                ],
            }
        }])
        assert docs_to_markdown(doc).strip() == "Hi **bold** there"

    def test_italic(self):
        doc = _doc_with([_paragraph("hi\n", text_style={"italic": True})])
        assert docs_to_markdown(doc).strip() == "*hi*"

    def test_link(self):
        doc = _doc_with([_paragraph(
            "click\n", text_style={"link": {"url": "https://example.com"}}
        )])
        assert docs_to_markdown(doc).strip() == "[click](https://example.com)"


def _bullet_paragraph(text, *, nesting_level=0, glyph="UNORDERED"):
    """Build a paragraph that's part of a bullet list."""
    return {
        "paragraph": {
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            "bullet": {
                "listId": "L1",
                "nestingLevel": nesting_level,
            },
            "elements": [{"textRun": {"content": text, "textStyle": {}}}],
        }
    }


class TestReaderLists:
    def test_unordered_list(self):
        doc = _doc_with([
            _bullet_paragraph("one\n"),
            _bullet_paragraph("two\n"),
        ])
        md = docs_to_markdown(doc)
        assert "- one" in md
        assert "- two" in md

    def test_nested_unordered(self):
        doc = _doc_with([
            _bullet_paragraph("one\n", nesting_level=0),
            _bullet_paragraph("nested\n", nesting_level=1),
        ])
        md = docs_to_markdown(doc)
        assert "- one" in md
        assert "  - nested" in md  # 2-space indent per level


class TestReaderTables:
    def test_simple_table(self):
        doc = _doc_with([{
            "table": {
                "tableRows": [
                    {"tableCells": [
                        {"content": [_paragraph("a\n")]},
                        {"content": [_paragraph("b\n")]},
                    ]},
                    {"tableCells": [
                        {"content": [_paragraph("1\n")]},
                        {"content": [_paragraph("2\n")]},
                    ]},
                ],
            }
        }])
        md = docs_to_markdown(doc)
        assert "| a | b |" in md
        assert "| --- | --- |" in md
        assert "| 1 | 2 |" in md
