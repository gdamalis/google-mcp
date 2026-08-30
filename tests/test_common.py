"""Unit tests for tools/docs/_common.py."""

import pytest

from tools.docs._common import parse_color, pt, end_index


class TestParseColor:
    def test_none_returns_none(self):
        assert parse_color(None) is None

    def test_long_hex(self):
        c = parse_color("#ff8800")
        assert c["red"] == 1.0
        assert abs(c["green"] - 0.5333) < 0.01
        assert c["blue"] == 0.0

    def test_short_hex(self):
        c = parse_color("#f80")
        assert c["red"] == 1.0

    def test_hex_without_hash(self):
        assert parse_color("ff0000") == parse_color("#ff0000")

    def test_named_color(self):
        c = parse_color("red")
        assert c == {"red": 1.0, "green": 0.0, "blue": 0.0}

    def test_named_with_underscore(self):
        assert parse_color("light_gray") is not None

    def test_invalid_hex_raises(self):
        with pytest.raises(ValueError, match="Unrecognized color"):
            parse_color("#xyz")

    def test_unknown_name_raises(self):
        with pytest.raises(ValueError):
            parse_color("mauve")


class TestPt:
    def test_none(self):
        assert pt(None) is None

    def test_positive(self):
        assert pt(12.5) == {"magnitude": 12.5, "unit": "PT"}

    def test_zero(self):
        assert pt(0) == {"magnitude": 0.0, "unit": "PT"}

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            pt(-1)


class TestEndIndex:
    def test_empty_doc(self):
        assert end_index({"body": {"content": []}}) == 1

    def test_one_paragraph(self):
        doc = {"body": {"content": [{"endIndex": 12}]}}
        assert end_index(doc) == 11

    def test_uses_last_element(self):
        doc = {"body": {"content": [
            {"endIndex": 5},
            {"endIndex": 20},
        ]}}
        assert end_index(doc) == 19


class TestU16Len:
    """The Docs API counts indices in UTF-16 code units, not code points."""

    def test_ascii_matches_len(self):
        from tools.docs._common import u16len
        assert u16len("Titulo") == 6

    def test_bmp_char_is_one_unit(self):
        from tools.docs._common import u16len
        # ✅ U+2705 and ❓ U+2753 sit inside the BMP.
        assert u16len("✅") == 1
        assert u16len("❓ Por confirmar") == len("❓ Por confirmar")

    def test_astral_char_is_two_units(self):
        from tools.docs._common import u16len
        # 📅 U+1F4C5 needs a surrogate pair; Python reports 1, the API sees 2.
        assert len("📅") == 1
        assert u16len("📅") == 2

    def test_heading_with_emoji(self):
        from tools.docs._common import u16len
        text = "📅 Cronograma de sesiones\n"
        assert u16len(text) == len(text) + 1

    def test_counts_each_astral_char(self):
        from tools.docs._common import u16len
        assert u16len("📅🎯📝") == 6
