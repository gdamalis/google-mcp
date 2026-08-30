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


KITCHEN_SINK = """# Title

This is a paragraph with **bold**, *italic*, ~~strike~~, `code`, and a [link](https://example.com).

## Subhead

- item one
- item two
  - nested
- item three

1. first
2. second

- [ ] todo
- [x] done

> A blockquote.

""" + "```" + """python
print("code block")
""" + "```" + """

---

| Name | Score |
|---|---|
| Alice | 10 |
| Bob | 7 |

![pic](https://example.com/p.png)
"""


class TestKitchenSink:
    def test_no_exceptions(self):
        reqs = markdown_to_requests(KITCHEN_SINK, insert_index=1)
        assert len(reqs) > 0

    def test_request_types_present(self):
        reqs = markdown_to_requests(KITCHEN_SINK, insert_index=1)
        types_present = set()
        for r in reqs:
            for k in r:
                types_present.add(k)
        assert "insertText" in types_present
        assert "updateParagraphStyle" in types_present
        assert "updateTextStyle" in types_present
        assert "createParagraphBullets" in types_present
        assert "insertTable" in types_present
        assert "insertInlineImage" in types_present


class TestRegressionBugs:
    """Regression tests for bugs found during end-to-end smoke verification."""

    def test_code_block_background_color_has_optional_color_shape(self):
        """Regression: shading.backgroundColor must be a full OptionalColor
        ({color: {rgbColor: {...}}}), not just the inner {rgbColor: {...}}.
        The Docs API rejects the inner-only form with 'Unknown name rgbColor'.
        Bug fix: _CODE_BG was being unwrapped to _CODE_BG['color'] before use."""
        md = "```\nfoo\n```"
        reqs = markdown_to_requests(md, insert_index=1)
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        shaded = [r for r in para_reqs
                  if r["updateParagraphStyle"]["paragraphStyle"].get("shading", {}).get("backgroundColor")]
        assert len(shaded) >= 1, "code block should produce a shaded paragraph"
        bg = shaded[0]["updateParagraphStyle"]["paragraphStyle"]["shading"]["backgroundColor"]
        # Must have outer 'color' wrapper — this is what OptionalColor requires.
        assert "color" in bg, f"backgroundColor must be OptionalColor with 'color' wrapper; got {bg!r}"
        assert "rgbColor" in bg["color"], f"OptionalColor.color must contain rgbColor; got {bg!r}"
        # Inner rgbColor must have the three components.
        rgb = bg["color"]["rgbColor"]
        assert "red" in rgb and "green" in rgb and "blue" in rgb


class TestPostTableShift:
    """Indices in requests AFTER a table need to be adjusted from the
    transformer's approximation to the real post-table doc position."""

    def test_shift_indices_helper(self):
        from tools.docs._markdown import _shift_indices
        requests = [
            {"insertText": {"location": {"index": 100}, "text": "hi"}},
            {"updateTextStyle": {
                "range": {"startIndex": 100, "endIndex": 102},
                "textStyle": {"bold": True},
                "fields": "bold",
            }},
            {"insertInlineImage": {"location": {"index": 105}, "uri": "x"}},
        ]
        _shift_indices(requests, shift=7)
        assert requests[0]["insertText"]["location"]["index"] == 107
        assert requests[1]["updateTextStyle"]["range"]["startIndex"] == 107
        assert requests[1]["updateTextStyle"]["range"]["endIndex"] == 109
        assert requests[2]["insertInlineImage"]["location"]["index"] == 112

    def test_shift_does_not_corrupt_non_index_ints(self):
        """rgbColor values, magnitudes, etc. are ints/floats — must not be shifted."""
        from tools.docs._markdown import _shift_indices
        requests = [{"updateParagraphStyle": {
            "range": {"startIndex": 10, "endIndex": 20},
            "paragraphStyle": {
                "shading": {"backgroundColor": {"color": {"rgbColor": {"red": 0, "green": 0, "blue": 0}}}},
                "indentStart": {"magnitude": 10, "unit": "PT"},
            },
            "fields": "shading.backgroundColor,indentStart",
        }}]
        _shift_indices(requests, shift=5)
        rng = requests[0]["updateParagraphStyle"]["range"]
        assert rng["startIndex"] == 15
        assert rng["endIndex"] == 25
        # rgb and magnitude untouched
        rgb = requests[0]["updateParagraphStyle"]["paragraphStyle"]["shading"]["backgroundColor"]["color"]["rgbColor"]
        assert rgb == {"red": 0, "green": 0, "blue": 0}
        mag = requests[0]["updateParagraphStyle"]["paragraphStyle"]["indentStart"]["magnitude"]
        assert mag == 10


class TestBulletWhitespaceConsumption:
    """Regression: createParagraphBullets consumes leading \\t chars from each
    paragraph in its range (uses them to compute nesting level, strips from
    content). The transformer must track this shrinkage so subsequent inserts
    use post-bullet indices.

    The bug manifested as 'Index N must be less than end index of segment N-X'
    when content appeared after a list with nested items."""

    def test_nested_list_then_paragraph_indices_align(self):
        md = (
            "- a\n"
            "  - nested-a\n"
            "  - nested-b\n"
            "- b\n"
            "\n"
            "after\n"
        )
        reqs = markdown_to_requests(md, insert_index=1)

        # Find createParagraphBullets and the request right after
        bullet_idx = next(i for i, r in enumerate(reqs) if "createParagraphBullets" in r)
        # Find the next insertText after the bullets request — its index must
        # reflect the post-consumption position.
        next_insert = None
        for r in reqs[bullet_idx + 1:]:
            if "insertText" in r:
                next_insert = r
                break
        assert next_insert is not None, "expected insertText for 'after' paragraph"

        # Bullets range
        rng = reqs[bullet_idx]["createParagraphBullets"]["range"]
        list_end = rng["endIndex"]

        # Two nested items each have a single \t prefix → 2 tabs consumed.
        # So the post-bullet cursor should be list_end - 2.
        next_index = next_insert["insertText"]["location"]["index"]
        assert next_index == list_end - 2, (
            f"after-list insertText should be at list_end - 2 = {list_end - 2}, "
            f"got {next_index}"
        )

    def test_no_nesting_no_shrinkage(self):
        """If no items have \\t prefix, no shrinkage should occur."""
        md = "- one\n- two\n\nafter\n"
        reqs = markdown_to_requests(md, insert_index=1)
        bullet_idx = next(i for i, r in enumerate(reqs) if "createParagraphBullets" in r)
        rng = reqs[bullet_idx]["createParagraphBullets"]["range"]
        next_insert = next(
            r for r in reqs[bullet_idx + 1:] if "insertText" in r
        )
        # No nested items → no tabs consumed → next insert at list_end.
        assert next_insert["insertText"]["location"]["index"] == rng["endIndex"]


class TestTableCellFillAlignment:
    """Regression: content after a table landed inside a table cell.

    Three separate defects, all in the same path:
      1. the post-table index was read from the doc BEFORE the cells were
         filled, so it described the empty table;
      2. `_shift_indices` skipped the `_pending_table` sentinel's own
         `insert_index`, so each further table measured its shift against a
         stale position;
      3. header-row bold ranges ignored the inserts that ran before them in
         the same batch.
    """

    # A 2x2 table at index 1. Cell content starts at 3, 5, 7, 9.
    @staticmethod
    def _doc(table_end):
        return {"body": {"content": [{
            "startIndex": 1,
            "endIndex": table_end,
            "table": {"tableRows": [
                {"tableCells": [
                    {"content": [{"startIndex": 3}]},
                    {"content": [{"startIndex": 5}]},
                ]},
                {"tableCells": [
                    {"content": [{"startIndex": 7}]},
                    {"content": [{"startIndex": 9}]},
                ]},
            ]},
        }]}}

    @staticmethod
    def _pending():
        return {
            "insert_index": 1, "rows": 2, "cols": 2, "header_row": 0,
            "cells": [
                {"text": "AB", "row": 0, "col": 0, "header": True},
                {"text": "CD", "row": 0, "col": 1, "header": True},
                {"text": "x", "row": 1, "col": 0, "header": False},
                {"text": "y", "row": 1, "col": 1, "header": False},
            ],
        }

    def test_cells_are_inserted_back_to_front(self):
        from tools.docs._markdown import _build_cell_fill_requests
        reqs = _build_cell_fill_requests(self._doc(13), self._pending())
        inserts = [r["insertText"]["location"]["index"] for r in reqs if "insertText" in r]
        assert inserts == [9, 7, 5, 3]

    def test_header_bold_accounts_for_earlier_inserts(self):
        from tools.docs._markdown import _build_cell_fill_requests
        reqs = _build_cell_fill_requests(self._doc(13), self._pending())
        ranges = [r["updateTextStyle"]["range"] for r in reqs if "updateTextStyle" in r]

        # "AB" stays at 3 — nothing is inserted before it. "CD" starts at 5 but
        # the two characters of "AB" go in first, so it ends up at 7.
        assert ranges[0] == {"startIndex": 3, "endIndex": 5}
        assert ranges[1] == {"startIndex": 7, "endIndex": 9}

    def test_shift_indices_moves_the_pending_table_sentinel(self):
        from tools.docs._markdown import _shift_indices
        requests = [{"_pending_table": {"insert_index": 40, "rows": 1, "cols": 2, "cells": []}}]
        _shift_indices(requests, shift=9)
        assert requests[0]["_pending_table"]["insert_index"] == 49

    def test_post_table_index_uses_the_filled_table(self):
        """The doc is re-read after the cell fill; content after the table is
        placed at the filled table's end, not the empty one's."""
        from unittest.mock import MagicMock
        from tools.docs._markdown import render_markdown_to_doc

        service = MagicMock()
        # First read: empty table ends at 13. Second: filled, ends at 25.
        service.documents.return_value.get.return_value.execute.side_effect = [
            self._doc(13), self._doc(25),
        ]
        service.documents.return_value.batchUpdate.return_value.execute.return_value = {}

        render_markdown_to_doc(service, "doc1", "| AB | CD |\n|---|---|\n| x | y |\n\nDespues.\n")

        batches = [
            c.kwargs["body"]["requests"]
            for c in service.documents.return_value.batchUpdate.call_args_list
        ]
        trailing = [
            r for batch in batches for r in batch
            if "insertText" in r and r["insertText"]["text"].startswith("Despues")
        ]
        assert trailing, "the paragraph after the table was never sent"
        # Transformer approximated 1 + (1 + 2*2*2 + 1) = 11; the real filled
        # table ends at 25, so the paragraph belongs there.
        assert trailing[0]["insertText"]["location"]["index"] == 25

    def test_document_is_read_twice_per_table(self):
        from unittest.mock import MagicMock
        from tools.docs._markdown import render_markdown_to_doc

        service = MagicMock()
        service.documents.return_value.get.return_value.execute.side_effect = [
            self._doc(13), self._doc(25),
        ]
        service.documents.return_value.batchUpdate.return_value.execute.return_value = {}

        render_markdown_to_doc(service, "doc1", "| AB | CD |\n|---|---|\n| x | y |\n\nDespues.\n")

        assert service.documents.return_value.get.return_value.execute.call_count == 2


class TestAstralCharacterIndices:
    """Regression: an emoji outside the BMP is two UTF-16 units to the Docs
    API but one code point to Python, so every index after it was one short.
    Content ran into the previous paragraph and heading styles bled onto the
    text that followed."""

    def test_cursor_advances_by_utf16_units(self):
        reqs = markdown_to_requests("## 📅 Cronograma\n\nTexto.\n", insert_index=1)
        inserts = [r["insertText"] for r in reqs if "insertText" in r]
        heading, para = inserts[0], inserts[1]

        assert heading["text"] == "📅 Cronograma\n"
        # 13 code points, 14 UTF-16 units. The paragraph belongs at 1 + 14.
        assert len(heading["text"]) == 13
        assert para["location"]["index"] == 15

    def test_heading_style_range_covers_the_whole_heading(self):
        reqs = markdown_to_requests("## 📅 Cronograma\n\nTexto.\n", insert_index=1)
        style = [r for r in reqs if "updateParagraphStyle" in r][0]
        assert style["updateParagraphStyle"]["range"] == {"startIndex": 1, "endIndex": 15}

    def test_bmp_emoji_is_unaffected(self):
        """❓ is inside the BMP, so nothing shifts."""
        reqs = markdown_to_requests("## ❓ Por confirmar\n\nTexto.\n", insert_index=1)
        inserts = [r["insertText"] for r in reqs if "insertText" in r]
        assert inserts[1]["location"]["index"] == 1 + len(inserts[0]["text"])

    def test_inline_style_range_after_an_emoji(self):
        reqs = markdown_to_requests("Hola 📅 con **negrita**.\n", insert_index=1)
        style = [r for r in reqs if "updateTextStyle" in r][0]["updateTextStyle"]
        text = [r for r in reqs if "insertText" in r][0]["insertText"]["text"]
        # "Hola 📅 con " is 11 code points but 12 UTF-16 units.
        assert text.index("negrita") == 11
        assert style["range"]["startIndex"] == 1 + 12
        assert style["range"]["endIndex"] == 1 + 12 + 7
