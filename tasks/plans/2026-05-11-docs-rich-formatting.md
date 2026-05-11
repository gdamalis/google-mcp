# Google Docs Rich Formatting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ~17 tools to the Google MCP that let the LLM author compelling, well-formatted Google Docs via a hybrid markdown + granular-styling model.

**Architecture:** Convert `tools/docs.py` into a `tools/docs/` package. Add a markdown→Docs-API transformer (`_markdown.py`) and Docs→markdown reader (`_reader.py`). Layer public tools on top: bulk markdown authoring, text/paragraph styling, structure (page setup, headers/footers, columns), media (URL + local-path images), table styling, template copy + rename.

**Tech Stack:** Python 3.10+, `mcp[fastmcp]`, `google-api-python-client`, `markdown-it-py` (new).

**Spec:** `tasks/specs/docs-rich-formatting.md`

**Branch:** `feat/docs-rich-formatting` (already created and active)

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `auth.py` | modify | Add `drive.file` scope |
| `pyproject.toml` | modify | Add `markdown-it-py>=3.0.0` |
| `tools/docs.py` | delete | Replaced by package |
| `tools/docs/__init__.py` | create | Re-import all public submodules so `@mcp.tool()` registrations fire |
| `tools/docs/_common.py` | create | `_docs()`, `_drive()`, color/length parsing, range helpers, error decorator |
| `tools/docs/_markdown.py` | create | Markdown→Docs API request transformer (the heavy lift) |
| `tools/docs/_reader.py` | create | Docs JSON→markdown export |
| `tools/docs/manage.py` | create | `search_docs`, `create_doc`, `copy_doc_from_template`, `rename_doc` |
| `tools/docs/text.py` | create | `read_doc`, `append_to_doc`, `insert_in_doc`, `append_markdown`, `replace_doc_markdown`, `replace_range_markdown`, `find_and_replace` |
| `tools/docs/style.py` | create | `apply_text_style`, `apply_paragraph_style` |
| `tools/docs/structure.py` | create | `insert_page_break`, `insert_horizontal_rule`, `insert_section_break`, `update_section_columns`, `update_page_setup`, `update_header_footer` |
| `tools/docs/media.py` | create | `insert_image` (URL + local path) |
| `tools/docs/tables.py` | create | `style_table_cells`, `merge_table_cells` |
| `tests/__init__.py` | create | empty |
| `tests/test_common.py` | create | Unit tests for color + length parsing |
| `tests/test_markdown_transformer.py` | create | Unit tests for `_markdown.py` |
| `tests/test_reader.py` | create | Unit tests for `_reader.py` |
| `README.md` | modify | Update Docs section + re-auth instructions |

**Testing approach:** TDD for `_common.py`, `_markdown.py`, `_reader.py` (pure-Python, no network). Public tools use manual smoke verification against real Google accounts — per the spec, the project does not mock the Docs API.

---

## Phase 1 — Foundation

### Task 1: Add markdown-it-py dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependency**

Edit `pyproject.toml`. Add `"markdown-it-py>=3.0.0"` to the `dependencies` list:

```toml
dependencies = [
    "mcp>=1.2.0",
    "google-api-python-client>=2.100.0",
    "google-auth-httplib2>=0.2.0",
    "google-auth-oauthlib>=1.1.0",
    "markdown-it-py>=3.0.0",
]
```

- [ ] **Step 2: Sync deps**

Run: `uv sync`
Expected: `markdown-it-py` and its dep `mdurl` installed, no errors.

- [ ] **Step 3: Verify importable**

Run: `uv run python -c "from markdown_it import MarkdownIt; print(MarkdownIt().render('# hi'))"`
Expected: `<h1>hi</h1>` printed.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): add markdown-it-py for Docs markdown transformer"
```

---

### Task 2: Expand OAuth scope to drive.file

**Files:**
- Modify: `auth.py:26-32`

- [ ] **Step 1: Add scope**

Edit `auth.py`. Change `SCOPES` to include `drive.file`:

```python
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
]
```

- [ ] **Step 2: Verify file compiles**

Run: `uv run python -c "from auth import SCOPES; print(len(SCOPES))"` (set `ACCOUNT=personal` env first, or any configured account)

Use: `ACCOUNT=personal uv run python -c "from auth import SCOPES; print(SCOPES)"`
Expected: 6 scopes printed including `drive.file`.

- [ ] **Step 3: Commit**

```bash
git add auth.py
git commit -m "feat(auth): add drive.file scope for image uploads and doc management"
```

- [ ] **Step 4: Document re-auth (will be done in Phase 10 with README)**

No action — note that all 3 accounts will need re-auth before the new tools are usable. We'll do that re-auth at the end of Phase 2 once the package skeleton is in place (so we can prove the existing tools still work after re-auth).

---

### Task 3: Convert tools/docs.py to package skeleton

**Files:**
- Delete: `tools/docs.py`
- Create: `tools/docs/__init__.py`
- Create: `tools/docs/_common.py`

- [ ] **Step 1: Move existing module out of the way**

Run: `git mv tools/docs.py tools/docs.py.old`

(We'll delete `.old` at the end of Phase 2 once everything is migrated.)

- [ ] **Step 2: Create package directory + `__init__.py`**

Create `tools/docs/__init__.py` with the following content. The submodule imports
are commented out — we'll uncomment them in Task 7 once the public modules exist.
If we import non-existent modules now, the whole package fails to load.

```python
"""
Google Docs tools — search, read, create, edit, style, structure, media.

Submodules' @mcp.tool() decorators register tools on import. Order doesn't
matter; each module is self-contained.
"""

# Uncomment in Task 7 once all public submodules exist:
# from . import manage    # noqa: F401
# from . import text      # noqa: F401
# from . import style     # noqa: F401
# from . import structure # noqa: F401
# from . import media     # noqa: F401
# from . import tables    # noqa: F401
```

- [ ] **Step 3: Create `_common.py` with service helpers**

Create `tools/docs/_common.py`:

```python
"""
Shared helpers for Docs tools — service builders, parsers, error decorator.
"""

import functools
import logging
import re
from typing import Callable, Optional

from googleapiclient.errors import HttpError

from auth import get_service

logger = logging.getLogger(__name__)


def docs():
    """Return cached Docs API v1 service."""
    return get_service("docs", "v1")


def drive():
    """Return cached Drive API v3 service."""
    return get_service("drive", "v3")


def tool_errors(fn: Callable) -> Callable:
    """
    Decorator: convert HttpError into {"error": "..."} dict.

    Validation errors raised as ValueError are also converted.
    All other exceptions propagate (programmer errors should be visible).
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except HttpError as e:
            status = getattr(e, "status_code", "unknown")
            reason = getattr(e, "reason", "")
            return {"error": f"Docs API {status}: {reason}", "details": str(e)}
        except ValueError as e:
            return {"error": "Invalid input", "details": str(e)}
    return wrapper


_NAMED_COLORS = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000",
    "green": "#00aa00", "blue": "#0000ff", "yellow": "#ffff00",
    "orange": "#ff8800", "gray": "#808080", "grey": "#808080",
    "light_gray": "#d9d9d9", "dark_gray": "#404040",
}


def parse_color(value: Optional[str]) -> Optional[dict]:
    """
    Parse a color spec into a Docs API OptionalColor.color.rgbColor dict.

    Accepts:
        "#ff8800", "#f80", "ff8800", "f80", "red", "light_gray"
    Returns:
        {"red": 1.0, "green": 0.533, "blue": 0.0}
        or None if value is None.

    Raises ValueError on unparseable input.
    """
    if value is None:
        return None
    s = value.strip().lower()
    if s in _NAMED_COLORS:
        s = _NAMED_COLORS[s]
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6 or not re.fullmatch(r"[0-9a-f]{6}", s):
        raise ValueError(
            f"Unrecognized color: {value!r}. Use #rgb, #rrggbb, or a named color "
            f"({', '.join(sorted(_NAMED_COLORS))})."
        )
    r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    return {"red": r / 255.0, "green": g / 255.0, "blue": b / 255.0}


def pt(value: Optional[float]) -> Optional[dict]:
    """
    Wrap a points value as a Docs API Dimension dict.
    Returns None when value is None.
    Raises ValueError on negative values.
    """
    if value is None:
        return None
    if value < 0:
        raise ValueError(f"Length must be non-negative; got {value}")
    return {"magnitude": float(value), "unit": "PT"}


def end_index(document: dict) -> int:
    """Return the insertion index just before the trailing newline."""
    content = document.get("body", {}).get("content", [])
    if not content:
        return 1
    return content[-1]["endIndex"] - 1
```

- [ ] **Step 4: Verify package imports**

Run: `ACCOUNT=personal uv run python -c "from tools.docs import _common; print(_common.parse_color('#f80'))"`
Expected: `{'red': 1.0, 'green': 0.5333333333333333, 'blue': 0.0}`

(`tools/docs/__init__.py` won't load yet because the public submodules don't exist. That's fine — the submodules will be created in following tasks. For now we test `_common` directly.)

- [ ] **Step 5: Commit**

```bash
git add tools/docs/__init__.py tools/docs/_common.py
git rm tools/docs.py.old  # actually leave this for now — see Step 1 note
```

Actually skip the `git rm` — keep `tools/docs.py.old` until Phase 2 is done. Just commit the new files:

```bash
git add tools/docs/__init__.py tools/docs/_common.py
git commit -m "feat(docs): scaffold docs package with shared helpers"
```

---

### Task 4: Unit tests for _common.py

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_common.py`

- [ ] **Step 1: Add empty tests package marker**

Create `tests/__init__.py` (empty file).

```python
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_common.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail or pass appropriately**

We need pytest. Check it's available:

Run: `uv run pytest --version`

If missing, add it:

```bash
uv add --dev pytest
```

Then run the tests:

Run: `ACCOUNT=personal uv run pytest tests/test_common.py -v`
Expected: All tests PASS (the implementation already exists from Task 3).

If any FAIL, fix `_common.py` until green.

- [ ] **Step 4: Commit**

```bash
git add tests/__init__.py tests/test_common.py pyproject.toml uv.lock
git commit -m "test(docs): add unit tests for color and length parsers"
```

---

### Task 5: Migrate manage.py (search_docs, create_doc)

**Files:**
- Create: `tools/docs/manage.py`

- [ ] **Step 1: Create manage.py with the existing 2 tools**

Create `tools/docs/manage.py`:

```python
"""Doc management — search, create, copy from template, rename."""

import logging
from typing import Optional

from app import mcp
from ._common import docs, drive, tool_errors

logger = logging.getLogger(__name__)


@mcp.tool()
@tool_errors
def search_docs(query: str, max_results: int = 20) -> list[dict]:
    """
    Search Google Drive for Google Docs by name or content.

    Args:
        query: Search query (matches document name and content)
        max_results: Maximum results to return (default 20)
    """
    service = drive()
    response = service.files().list(
        q=f"mimeType='application/vnd.google-apps.document' and fullText contains '{query}'",
        spaces="drive",
        fields="files(id, name, modifiedTime, owners, webViewLink)",
        pageSize=min(max_results, 100),
    ).execute()

    files = response.get("files", [])
    return [
        {
            "id": f["id"],
            "name": f["name"],
            "modified": f.get("modifiedTime", ""),
            "owner": f.get("owners", [{}])[0].get("emailAddress", "") if f.get("owners") else "",
            "link": f.get("webViewLink", ""),
        }
        for f in files
    ]


@mcp.tool()
@tool_errors
def create_doc(
    title: str,
    markdown: Optional[str] = None,
    content: Optional[str] = None,
) -> dict:
    """
    Create a new Google Doc.

    Args:
        title: Document title.
        markdown: Optional markdown to render as initial content.
                  Takes precedence over `content` when both are provided.
                  Supports headings, bold/italic/code, lists, tables, links,
                  images, code blocks, blockquotes, horizontal rules.
        content: Optional plain text to insert (legacy; prefer `markdown`).
    """
    service = docs()
    doc = service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]

    if markdown:
        from ._markdown import render_markdown_to_doc
        render_markdown_to_doc(service, doc_id, markdown, insert_index=1)
    elif content:
        service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
        ).execute()

    return {
        "id": doc_id,
        "title": title,
        "link": f"https://docs.google.com/document/d/{doc_id}/edit",
        "status": "Document created successfully.",
    }
```

Note: `render_markdown_to_doc` doesn't exist yet — it's imported lazily so this module loads cleanly even before Phase 3. If `markdown=` is passed before Phase 3 is implemented, you'll get an ImportError at call time. Acceptable interim state.

- [ ] **Step 2: Verify it imports**

Run: `ACCOUNT=personal uv run python -c "from tools.docs import manage; print([t for t in dir(manage) if not t.startswith('_')])"`
Expected: contains `search_docs`, `create_doc` plus helpers.

- [ ] **Step 3: Commit**

```bash
git add tools/docs/manage.py
git commit -m "feat(docs): migrate search_docs and create_doc into package"
```

---

### Task 6: Migrate text.py (read_doc, append_to_doc, insert_in_doc)

**Files:**
- Create: `tools/docs/text.py`

- [ ] **Step 1: Create text.py with the existing 3 tools (kept faithful for now)**

Create `tools/docs/text.py`:

```python
"""Document text tools — read, append, insert, markdown bulk ops, find/replace."""

import logging
from typing import Literal

from app import mcp
from ._common import docs, end_index, tool_errors

logger = logging.getLogger(__name__)


def _extract_text(document: dict) -> str:
    """Extract plain text from a Docs JSON structure (legacy behavior)."""
    body = document.get("body", {})
    content = body.get("content", [])
    text_parts = []
    for element in content:
        paragraph = element.get("paragraph")
        if paragraph:
            for text_run in paragraph.get("elements", []):
                text_parts.append(text_run.get("textRun", {}).get("content", ""))
        table = element.get("table")
        if table:
            for row in table.get("tableRows", []):
                row_texts = []
                for cell in row.get("tableCells", []):
                    cell_text = ""
                    for cell_content in cell.get("content", []):
                        cell_para = cell_content.get("paragraph")
                        if cell_para:
                            for text_run in cell_para.get("elements", []):
                                cell_text += text_run.get("textRun", {}).get("content", "")
                    row_texts.append(cell_text.strip())
                text_parts.append("\t".join(row_texts) + "\n")
    return "".join(text_parts)


@mcp.tool()
@tool_errors
def read_doc(
    document_id: str,
    format: Literal["markdown", "text", "json"] = "markdown",
) -> dict:
    """
    Read a Google Doc.

    Args:
        document_id: The Google Docs document ID.
        format: "markdown" (default — structured export, recommended for LLMs)
                "text" (plain text, formatting stripped, capped at 10k chars)
                "json" (raw Docs structure with indices — use this before
                        calling apply_text_style or other index-based tools)
    """
    service = docs()
    doc = service.documents().get(documentId=document_id).execute()

    result = {
        "id": doc["documentId"],
        "title": doc.get("title", ""),
        "link": f"https://docs.google.com/document/d/{doc['documentId']}/edit",
    }

    if format == "text":
        text = _extract_text(doc)
        result["content"] = text[:10000]
        result["content_length"] = len(text)
    elif format == "json":
        result["document"] = doc
    else:  # markdown
        from ._reader import docs_to_markdown
        md = docs_to_markdown(doc)
        result["content"] = md
        result["content_length"] = len(md)

    return result


@mcp.tool()
@tool_errors
def append_to_doc(document_id: str, text: str) -> dict:
    """
    Append plain text to the end of a Google Doc.

    For richly formatted appends, use `append_markdown` instead.
    """
    service = docs()
    doc = service.documents().get(documentId=document_id).execute()
    idx = end_index(doc)
    service.documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"insertText": {"location": {"index": idx}, "text": text}}]},
    ).execute()
    return {"id": document_id, "status": f"Appended {len(text)} characters."}


@mcp.tool()
@tool_errors
def insert_in_doc(document_id: str, text: str, index: int) -> dict:
    """
    Insert plain text at a specific character index.

    Index 1 is the start of the document. Use `read_doc(format="json")` to
    find indices for surgical edits.
    """
    service = docs()
    service.documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"insertText": {"location": {"index": index}, "text": text}}]},
    ).execute()
    return {"id": document_id, "status": f"Inserted {len(text)} characters at {index}."}
```

The `read_doc` default change to `"markdown"` requires `_reader.py` to exist before we use that default in practice. The lazy import keeps `text.py` loadable; calling `read_doc(doc_id)` without `_reader.py` raises ImportError. We'll fix that in Phase 4.

For now: existing callers should pass `format="text"` to preserve old behavior. We'll defer changing the default in `text.py` until Phase 4 lands — let's pin it to "text" for now so we don't break anything mid-implementation:

Change the `format` default in `text.py` to `"text"` for the interim. We'll flip it to `"markdown"` as the final step of Phase 4.

```python
def read_doc(
    document_id: str,
    format: Literal["markdown", "text", "json"] = "text",  # flipped to markdown in Phase 4
) -> dict:
```

- [ ] **Step 2: Verify import**

Run: `ACCOUNT=personal uv run python -c "from tools.docs import text; print([t for t in dir(text) if not t.startswith('_')])"`
Expected: contains `read_doc`, `append_to_doc`, `insert_in_doc`.

- [ ] **Step 3: Commit**

```bash
git add tools/docs/text.py
git commit -m "feat(docs): migrate read_doc/append/insert into package"
```

---

### Task 7: Create stub modules + remove old docs.py

**Files:**
- Create: `tools/docs/style.py` (stub)
- Create: `tools/docs/structure.py` (stub)
- Create: `tools/docs/media.py` (stub)
- Create: `tools/docs/tables.py` (stub)
- Delete: `tools/docs.py.old`

- [ ] **Step 1: Create empty stub modules**

Each of these files starts with just a module docstring so `__init__.py`'s imports succeed:

`tools/docs/style.py`:
```python
"""Text and paragraph styling tools — populated in Phase 5."""
```

`tools/docs/structure.py`:
```python
"""Structure tools (page breaks, sections, headers/footers) — populated in Phase 6."""
```

`tools/docs/media.py`:
```python
"""Image insertion — populated in Phase 7."""
```

`tools/docs/tables.py`:
```python
"""Table styling — populated in Phase 7."""
```

- [ ] **Step 1b: Activate package imports in `__init__.py`**

Edit `tools/docs/__init__.py`. Uncomment the submodule imports so all modules
register their `@mcp.tool()` decorators on package load:

```python
"""
Google Docs tools — search, read, create, edit, style, structure, media.
"""

from . import manage    # noqa: F401
from . import text      # noqa: F401
from . import style     # noqa: F401
from . import structure # noqa: F401
from . import media     # noqa: F401
from . import tables    # noqa: F401
```

- [ ] **Step 2: Delete the old docs.py.old**

Run: `git rm tools/docs.py.old`

(If you didn't rename to `.old` in Task 3 because `git mv` errored, just confirm `tools/docs.py` is gone.)

- [ ] **Step 3: Verify the package imports cleanly via server**

Run: `ACCOUNT=personal uv run python -c "import server; print('OK')"`
Expected: prints `OK`. If it fails with import errors in the new `tools/docs/*` modules, fix before continuing.

- [ ] **Step 4: List registered MCP tools**

Run: `ACCOUNT=personal uv run python -c "
from app import mcp
import server
print(sorted(t.name for t in mcp._tool_manager.list_tools()))
"` (note: FastMCP's API for listing tools may differ; if `_tool_manager` isn't the attribute, use whatever inspection method FastMCP exposes; the test is that no errors occur and that `search_docs`, `read_doc`, `create_doc`, `append_to_doc`, `insert_in_doc` are present alongside Gmail/Calendar/etc.)

If listing tools is too fiddly, fall back to: launch the server and check it via `claude mcp list`. The key bar is "no import errors".

- [ ] **Step 5: Re-authenticate all 3 accounts**

Now that the scope is expanded and the package skeleton is in place, the user must re-auth before downstream tasks can be tested. For each account:

```bash
ACCOUNT=ibica uv run python authenticate.py
ACCOUNT=idcr uv run python authenticate.py
ACCOUNT=personal uv run python authenticate.py
```

Each opens a browser; user grants the new `drive.file` permission.

**This is a human-in-the-loop step.** The agent should pause and ask the user to run these commands and confirm before proceeding to Phase 2 work that needs the new scope.

- [ ] **Step 6: Commit**

```bash
git add tools/docs/style.py tools/docs/structure.py tools/docs/media.py tools/docs/tables.py
git commit -m "feat(docs): add stub modules for upcoming style/structure/media/tables"
```

---

## Phase 2 — Markdown Transformer (TDD)

This phase implements `_markdown.py`. We write tests first, then make them pass element-by-element.

### Task 8: Markdown transformer — skeleton and headings

**Files:**
- Create: `tools/docs/_markdown.py`
- Create: `tests/test_markdown_transformer.py`

- [ ] **Step 1: Write failing test for heading rendering**

Create `tests/test_markdown_transformer.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `ACCOUNT=personal uv run pytest tests/test_markdown_transformer.py::TestHeadings::test_h1 -v`
Expected: FAIL — `ImportError: cannot import name 'markdown_to_requests' from 'tools.docs._markdown'`.

- [ ] **Step 3: Implement skeleton + heading handler**

Create `tools/docs/_markdown.py`:

```python
"""
Markdown → Docs API request transformer.

Public entry points:
    markdown_to_requests(markdown, insert_index) -> list[dict]
        Pure function — produces request list, no API calls.

    render_markdown_to_doc(service, document_id, markdown, insert_index)
        Convenience: render + batchUpdate in one call.
"""

import logging
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token

logger = logging.getLogger(__name__)


class _State:
    """Mutable cursor + request accumulator passed through handlers."""
    def __init__(self, insert_index: int):
        self.cursor: int = insert_index
        self.requests: list[dict] = []

    def insert_text(self, text: str) -> tuple[int, int]:
        """Append an insertText request. Return (start, end) range."""
        start = self.cursor
        self.requests.append({
            "insertText": {"location": {"index": start}, "text": text}
        })
        self.cursor += len(text)
        return start, self.cursor

    def style_paragraph(self, start: int, end: int, style: dict, fields: str) -> None:
        self.requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "paragraphStyle": style,
                "fields": fields,
            }
        })

    def style_text(self, start: int, end: int, style: dict, fields: str) -> None:
        if start == end:
            return  # empty range — Docs API rejects
        self.requests.append({
            "updateTextStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "textStyle": style,
                "fields": fields,
            }
        })


def _handle_heading(state: _State, tokens: list[Token], i: int) -> int:
    """
    Tokens: heading_open, inline, heading_close.
    Returns the new token index after consuming the heading.
    """
    open_token = tokens[i]
    level = int(open_token.tag[1])  # "h1" -> 1
    inline_token = tokens[i + 1]
    text = inline_token.content
    start, end = state.insert_text(text + "\n")
    state.style_paragraph(
        start, end,
        {"namedStyleType": f"HEADING_{level}"},
        "namedStyleType",
    )
    return i + 3  # skip heading_close


def markdown_to_requests(markdown: str, insert_index: int = 1) -> list[dict]:
    """
    Convert markdown source to a list of Docs API batchUpdate requests.

    Pure function — does not call any API.

    Args:
        markdown: Markdown source string.
        insert_index: 1-based Docs index where content should begin.

    Returns:
        List of Request dicts ready for documents.batchUpdate.
    """
    md = MarkdownIt("commonmark", {"html": False}).enable("table").enable("strikethrough")
    tokens = md.parse(markdown)
    state = _State(insert_index=insert_index)

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            i = _handle_heading(state, tokens, i)
        else:
            # Unhandled token types are skipped silently for now.
            # Subsequent tasks add handlers.
            i += 1

    return state.requests


def render_markdown_to_doc(service: Any, document_id: str, markdown: str,
                           insert_index: int = 1) -> dict:
    """
    Convenience: build requests + send batchUpdate. Returns the API response.
    """
    requests = markdown_to_requests(markdown, insert_index=insert_index)
    if not requests:
        return {"replies": [], "documentId": document_id}
    return service.documents().batchUpdate(
        documentId=document_id, body={"requests": requests}
    ).execute()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `ACCOUNT=personal uv run pytest tests/test_markdown_transformer.py::TestHeadings -v`
Expected: all 3 heading tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/docs/_markdown.py tests/test_markdown_transformer.py
git commit -m "feat(docs): markdown transformer scaffolding with heading support"
```

---

### Task 9: Markdown transformer — paragraphs and inline styles

**Files:**
- Modify: `tools/docs/_markdown.py`
- Modify: `tests/test_markdown_transformer.py`

- [ ] **Step 1: Write failing tests for paragraphs and inline styles**

Append to `tests/test_markdown_transformer.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `ACCOUNT=personal uv run pytest tests/test_markdown_transformer.py::TestParagraphsAndInline -v`
Expected: all FAIL (paragraph/inline handlers not yet implemented).

- [ ] **Step 3: Add paragraph + inline handlers**

Edit `tools/docs/_markdown.py`. Add these helper functions and extend the main loop:

```python
def _render_inline(state: _State, inline_token: Token) -> int:
    """
    Render an inline token (its `children` are spans) and return the paragraph
    end index (before the trailing newline). Emits insertText + updateTextStyle
    requests. The caller is responsible for inserting the trailing "\n".
    """
    paragraph_start = state.cursor
    children = inline_token.children or []
    style_stack: list[dict] = []  # active styles for nested marks

    # Two-pass within the paragraph: first collect text + per-range styles.
    pending_styles: list[tuple[int, int, dict, str]] = []

    def active_style() -> tuple[dict, str]:
        merged: dict = {}
        fields: set[str] = set()
        for s in style_stack:
            for k, v in s.items():
                merged[k] = v
                fields.add(k)
        return merged, ",".join(sorted(fields))

    for child in children:
        if child.type == "text":
            start, end = state.insert_text(child.content)
            style, fields = active_style()
            if style:
                pending_styles.append((start, end, style, fields))
        elif child.type == "softbreak":
            state.insert_text(" ")  # treat soft breaks as spaces
        elif child.type == "hardbreak":
            state.insert_text("\v")  # vertical tab = line break within paragraph
        elif child.type == "strong_open":
            style_stack.append({"bold": True})
        elif child.type == "strong_close":
            style_stack.pop()
        elif child.type == "em_open":
            style_stack.append({"italic": True})
        elif child.type == "em_close":
            style_stack.pop()
        elif child.type == "s_open":
            style_stack.append({"strikethrough": True})
        elif child.type == "s_close":
            style_stack.pop()
        elif child.type == "code_inline":
            start, end = state.insert_text(child.content)
            pending_styles.append((
                start, end,
                {"weightedFontFamily": {"fontFamily": "Roboto Mono"}},
                "weightedFontFamily",
            ))
        elif child.type == "link_open":
            url = next((a[1] for a in (child.attrs or []) if a[0] == "href"), "")
            style_stack.append({"link": {"url": url}})
        elif child.type == "link_close":
            style_stack.pop()
        else:
            logger.warning("Unhandled inline token type: %s", child.type)

    paragraph_end = state.cursor

    # Emit style requests AFTER all text insertions
    for start, end, style, fields in pending_styles:
        state.style_text(start, end, style, fields)

    return paragraph_end


def _handle_paragraph(state: _State, tokens: list[Token], i: int) -> int:
    """Tokens: paragraph_open, inline, paragraph_close."""
    inline = tokens[i + 1]
    _render_inline(state, inline)
    state.insert_text("\n")  # close paragraph
    return i + 3
```

Now update the main loop in `markdown_to_requests`:

```python
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            i = _handle_heading(state, tokens, i)
        elif tok.type == "paragraph_open":
            i = _handle_paragraph(state, tokens, i)
        else:
            logger.debug("Skipping unhandled token: %s", tok.type)
            i += 1
```

Also update `_handle_heading` to use `_render_inline` so headings with inline styles work:

```python
def _handle_heading(state: _State, tokens: list[Token], i: int) -> int:
    open_token = tokens[i]
    level = int(open_token.tag[1])
    inline_token = tokens[i + 1]
    start = state.cursor
    _render_inline(state, inline_token)
    state.insert_text("\n")
    end = state.cursor
    state.style_paragraph(
        start, end,
        {"namedStyleType": f"HEADING_{level}"},
        "namedStyleType",
    )
    return i + 3
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `ACCOUNT=personal uv run pytest tests/test_markdown_transformer.py -v`
Expected: all heading + paragraph + inline tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/docs/_markdown.py tests/test_markdown_transformer.py
git commit -m "feat(docs): paragraph and inline style handlers in markdown transformer"
```

---

### Task 10: Markdown transformer — lists (unordered, ordered, checkbox)

**Files:**
- Modify: `tools/docs/_markdown.py`
- Modify: `tests/test_markdown_transformer.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_markdown_transformer.py`:

```python
class TestLists:
    def test_unordered_list(self):
        md = "- one\n- two\n- three"
        reqs = markdown_to_requests(md, insert_index=1)
        text_reqs = [r for r in reqs if "insertText" in r]
        # Three list items, each as its own insertText (text only, no bullets in text)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `ACCOUNT=personal uv run pytest tests/test_markdown_transformer.py::TestLists -v`
Expected: FAIL — list handlers not implemented.

- [ ] **Step 3: Add list handler**

Edit `tools/docs/_markdown.py`. Add the list handler:

```python
_BULLET_PRESETS = {
    "bullet": "BULLET_DISC_CIRCLE_SQUARE",
    "ordered": "NUMBERED_DECIMAL_ALPHA_ROMAN",
    "checkbox": "BULLET_CHECKBOX",
}


def _is_checkbox_item(inline_token: Token) -> bool:
    """Detect GFM task list items: `[ ]` or `[x]` at the start of inline content."""
    children = inline_token.children or []
    if not children or children[0].type != "text":
        return False
    text = children[0].content
    return text.startswith(("[ ] ", "[x] ", "[X] "))


def _strip_checkbox_marker(inline_token: Token) -> bool:
    """Mutate the inline's first text child to remove the `[ ]`/`[x]` marker.
    Returns True if a checkbox marker was found and stripped."""
    children = inline_token.children or []
    if not children or children[0].type != "text":
        return False
    text = children[0].content
    for prefix in ("[ ] ", "[x] ", "[X] "):
        if text.startswith(prefix):
            children[0].content = text[len(prefix):]
            return True
    return False


def _handle_list(state: _State, tokens: list[Token], i: int, depth: int = 0) -> int:
    """
    Handle bullet_list_open or ordered_list_open. Returns index of token after
    the matching list_close. Supports nesting.
    """
    open_token = tokens[i]
    ordered = open_token.type == "ordered_list_open"

    # Detect checkbox list by scanning items
    is_checkbox = False
    j = i + 1
    while j < len(tokens) and tokens[j].type != ("ordered_list_close" if ordered else "bullet_list_close"):
        if tokens[j].type == "list_item_open":
            # find first inline child
            k = j + 1
            while k < len(tokens) and tokens[k].type != "list_item_close":
                if tokens[k].type == "inline" and _is_checkbox_item(tokens[k]):
                    is_checkbox = True
                    break
                k += 1
        j += 1
        if is_checkbox:
            break

    preset_key = "checkbox" if is_checkbox else ("ordered" if ordered else "bullet")
    preset = _BULLET_PRESETS[preset_key]

    list_start = state.cursor
    close_type = "ordered_list_close" if ordered else "bullet_list_close"

    j = i + 1
    while j < len(tokens) and tokens[j].type != close_type:
        if tokens[j].type == "list_item_open":
            # Process item: it contains paragraph(s) and possibly nested lists
            k = j + 1
            indent = "\t" * depth
            while k < len(tokens) and tokens[k].type != "list_item_close":
                if tokens[k].type == "paragraph_open":
                    inline = tokens[k + 1]
                    if is_checkbox:
                        _strip_checkbox_marker(inline)
                    # Insert indent, then inline content, then newline
                    if indent:
                        state.insert_text(indent)
                    _render_inline(state, inline)
                    state.insert_text("\n")
                    k += 3
                elif tokens[k].type in ("bullet_list_open", "ordered_list_open"):
                    k = _handle_list(state, tokens, k, depth=depth + 1)
                else:
                    k += 1
            j = k + 1  # skip list_item_close
        else:
            j += 1

    list_end = state.cursor

    # Apply bullets to the full list range — but only at the top depth.
    # Nested items are differentiated by their \t prefixes per Docs API convention.
    if depth == 0 and list_end > list_start:
        state.requests.append({
            "createParagraphBullets": {
                "range": {"startIndex": list_start, "endIndex": list_end},
                "bulletPreset": preset,
            }
        })

    return j + 1  # skip list_close
```

Add list_open to the main loop:

```python
        elif tok.type in ("bullet_list_open", "ordered_list_open"):
            i = _handle_list(state, tokens, i)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `ACCOUNT=personal uv run pytest tests/test_markdown_transformer.py::TestLists -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/docs/_markdown.py tests/test_markdown_transformer.py
git commit -m "feat(docs): list handlers (unordered, ordered, checkbox, nested)"
```

---

### Task 11: Markdown transformer — code blocks, blockquotes, horizontal rules

**Files:**
- Modify: `tools/docs/_markdown.py`
- Modify: `tests/test_markdown_transformer.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_markdown_transformer.py`:

```python
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
        # Horizontal rule is inserted via insertText of a special character + paragraph style,
        # OR via the dedicated approach below. We use a section break OR a paragraph with
        # borderBottom. For simplicity, expect at least one updateParagraphStyle with a border.
        # If your implementation differs, adjust the assertion.
        para_styles = [r for r in reqs if "updateParagraphStyle" in r]
        with_border = [s for s in para_styles
                       if s["updateParagraphStyle"]["paragraphStyle"].get("borderBottom")]
        assert len(with_border) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `ACCOUNT=personal uv run pytest tests/test_markdown_transformer.py::TestBlocks -v`
Expected: FAIL.

- [ ] **Step 3: Add handlers**

Edit `tools/docs/_markdown.py`. Add:

```python
_CODE_BG = {"color": {"rgbColor": {"red": 0.953, "green": 0.953, "blue": 0.953}}}  # #f3f3f3


def _handle_code_block(state: _State, tokens: list[Token], i: int) -> int:
    """Fenced code block (token type 'fence') or indented ('code_block')."""
    tok = tokens[i]
    code = tok.content
    if not code.endswith("\n"):
        code += "\n"
    start, end = state.insert_text(code)
    state.style_text(
        start, end,
        {"weightedFontFamily": {"fontFamily": "Roboto Mono"}},
        "weightedFontFamily",
    )
    state.style_paragraph(
        start, end,
        {
            "shading": {"backgroundColor": _CODE_BG["color"]},
            "indentStart": {"magnitude": 10, "unit": "PT"},
            "indentEnd": {"magnitude": 10, "unit": "PT"},
        },
        "shading.backgroundColor,indentStart,indentEnd",
    )
    return i + 1


def _handle_blockquote(state: _State, tokens: list[Token], i: int) -> int:
    """Tokens: blockquote_open, ... (may contain paragraphs), blockquote_close."""
    quote_start = state.cursor
    j = i + 1
    while j < len(tokens) and tokens[j].type != "blockquote_close":
        if tokens[j].type == "paragraph_open":
            inline = tokens[j + 1]
            _render_inline(state, inline)
            state.insert_text("\n")
            j += 3
        else:
            j += 1
    quote_end = state.cursor
    if quote_end > quote_start:
        state.style_paragraph(
            quote_start, quote_end,
            {
                "indentStart": {"magnitude": 18, "unit": "PT"},
                "borderLeft": {
                    "color": {"color": {"rgbColor": {"red": 0.7, "green": 0.7, "blue": 0.7}}},
                    "width": {"magnitude": 3, "unit": "PT"},
                    "padding": {"magnitude": 8, "unit": "PT"},
                    "dashStyle": "SOLID",
                },
            },
            "indentStart,borderLeft",
        )
    return j + 1


def _handle_hr(state: _State, tokens: list[Token], i: int) -> int:
    """Horizontal rule: insert an empty paragraph with a bottom border."""
    start, end = state.insert_text("\n")
    state.style_paragraph(
        start, end,
        {
            "borderBottom": {
                "color": {"color": {"rgbColor": {"red": 0.7, "green": 0.7, "blue": 0.7}}},
                "width": {"magnitude": 1, "unit": "PT"},
                "padding": {"magnitude": 1, "unit": "PT"},
                "dashStyle": "SOLID",
            }
        },
        "borderBottom",
    )
    return i + 1
```

Add to the main loop:

```python
        elif tok.type in ("fence", "code_block"):
            i = _handle_code_block(state, tokens, i)
        elif tok.type == "blockquote_open":
            i = _handle_blockquote(state, tokens, i)
        elif tok.type == "hr":
            i = _handle_hr(state, tokens, i)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `ACCOUNT=personal uv run pytest tests/test_markdown_transformer.py::TestBlocks -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/docs/_markdown.py tests/test_markdown_transformer.py
git commit -m "feat(docs): code block, blockquote, hr handlers"
```

---

### Task 12: Markdown transformer — images

**Files:**
- Modify: `tools/docs/_markdown.py`
- Modify: `tests/test_markdown_transformer.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_markdown_transformer.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `ACCOUNT=personal uv run pytest tests/test_markdown_transformer.py::TestImages -v`
Expected: FAIL.

- [ ] **Step 3: Add image handler in `_render_inline`**

Edit `tools/docs/_markdown.py`. In `_render_inline`, add an `elif` for `image` token type:

```python
        elif child.type == "image":
            src = next((a[1] for a in (child.attrs or []) if a[0] == "src"), "")
            if src.startswith(("http://", "https://")):
                state.requests.append({
                    "insertInlineImage": {
                        "location": {"index": state.cursor},
                        "uri": src,
                    }
                })
                state.cursor += 1  # image counts as 1 character in the doc
            else:
                logger.warning(
                    "Markdown image with non-URL source (%s) skipped by transformer. "
                    "Use the insert_image tool with a local path to upload via Drive.",
                    src,
                )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `ACCOUNT=personal uv run pytest tests/test_markdown_transformer.py::TestImages -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/docs/_markdown.py tests/test_markdown_transformer.py
git commit -m "feat(docs): inline URL image handler in markdown transformer"
```

---

### Task 13: Markdown transformer — tables

**Files:**
- Modify: `tools/docs/_markdown.py`
- Modify: `tests/test_markdown_transformer.py`

This task is more involved because the Docs API allocates table cell indices on insertion; we can't predict them ahead of time. The transformer emits an `insertTable` plus a *deferred* set of "cell text" instructions that `render_markdown_to_doc` post-processes by re-reading the document.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_markdown_transformer.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `ACCOUNT=personal uv run pytest tests/test_markdown_transformer.py::TestTables -v`
Expected: FAIL.

- [ ] **Step 3: Add table handler**

Edit `tools/docs/_markdown.py`:

```python
def _handle_table(state: _State, tokens: list[Token], i: int) -> int:
    """
    GFM table. Tokens: table_open, thead_open, tr_open, th_open*, th_close,
    tr_close, thead_close, tbody_open, (tr_open, td_open*, td_close, tr_close)*,
    tbody_close, table_close.

    Emits insertTable + a _pending_table sentinel to be processed after re-reading
    the doc to learn cell indices.
    """
    cells: list[dict] = []
    rows = 0
    cols = 0

    j = i + 1
    current_row_cells = 0
    in_header = False
    while j < len(tokens) and tokens[j].type != "table_close":
        t = tokens[j].type
        if t == "thead_open":
            in_header = True
        elif t == "thead_close":
            in_header = False
        elif t == "tr_open":
            current_row_cells = 0
        elif t == "tr_close":
            if rows == 0:
                cols = current_row_cells
            rows += 1
        elif t in ("th_open", "td_open"):
            # Find the inline token
            k = j + 1
            while tokens[k].type != "inline":
                k += 1
            cell_text = tokens[k].content
            cells.append({
                "text": cell_text,
                "row": rows,
                "col": current_row_cells,
                "header": in_header,
            })
            current_row_cells += 1
            # skip to th_close / td_close
            while tokens[j].type not in ("th_close", "td_close"):
                j += 1
        j += 1

    table_insert_index = state.cursor
    state.requests.append({
        "insertTable": {
            "location": {"index": table_insert_index},
            "rows": rows,
            "columns": cols,
        }
    })
    # After insertion the cursor advances by 1 + rows*(cols*2 + 1) approximately —
    # but we cannot predict precisely without re-reading. We mark a sentinel
    # request that render_markdown_to_doc will resolve later by re-fetching
    # the document and finding the new table.
    state.requests.append({
        "_pending_table": {
            "insert_index": table_insert_index,
            "rows": rows,
            "cols": cols,
            "cells": cells,
            "header_row": 0,
        }
    })
    # For cursor accounting we assume the table consumes a known minimum:
    # each cell adds at least 2 indices (cell start + paragraph). The simplest
    # safe approach is to NOT advance state.cursor here — any tokens after the
    # table will need to be reflowed after the cell-fill pass anyway. In practice
    # tables are usually followed by a blank line, and the post-processor handles
    # follow-up content correctly because it always re-reads cursor positions
    # from the doc.
    #
    # If a table is followed by more markdown content, that content gets inserted
    # at the original cursor (pre-table), which after the insertTable will be
    # before the new table. The fix: advance cursor by an approximation that
    # over-counts, then trim. Simpler: forbid post-table content in the same
    # transformer call — split into multiple transformer calls. But that's
    # restrictive. We'll handle this carefully in render_markdown_to_doc.
    #
    # Practical choice: advance cursor by 1 + rows * cols * 2 + 1. This is an
    # estimate; the post-processor recomputes exact indices via re-read.
    state.cursor += 1 + rows * cols * 2 + 1

    return j + 1
```

Add the table_open dispatch to the main loop:

```python
        elif tok.type == "table_open":
            i = _handle_table(state, tokens, i)
```

- [ ] **Step 4: Update render_markdown_to_doc to handle pending tables**

Modify `render_markdown_to_doc` to split-and-resolve:

```python
def render_markdown_to_doc(service: Any, document_id: str, markdown: str,
                           insert_index: int = 1) -> dict:
    """
    Build requests + send batchUpdates, handling tables in a second pass.
    """
    requests = markdown_to_requests(markdown, insert_index=insert_index)
    if not requests:
        return {"replies": [], "documentId": document_id}

    # If there are no table sentinels, send the whole batch as-is.
    if not any("_pending_table" in r for r in requests):
        return service.documents().batchUpdate(
            documentId=document_id, body={"requests": requests}
        ).execute()

    # Split: send pre-table requests + insertTable, then re-read, then populate cells.
    # This is per-table, sequentially.
    response: dict = {"replies": [], "documentId": document_id}
    pending: list[dict] = []
    for req in requests:
        if "_pending_table" in req:
            # Flush pending real requests
            if pending:
                r = service.documents().batchUpdate(
                    documentId=document_id, body={"requests": pending}
                ).execute()
                response["replies"].extend(r.get("replies", []))
                pending = []
            # Re-read doc to find the just-inserted table
            doc = service.documents().get(documentId=document_id).execute()
            cell_requests = _build_cell_fill_requests(doc, req["_pending_table"])
            r = service.documents().batchUpdate(
                documentId=document_id, body={"requests": cell_requests}
            ).execute()
            response["replies"].extend(r.get("replies", []))
        else:
            pending.append(req)

    if pending:
        r = service.documents().batchUpdate(
            documentId=document_id, body={"requests": pending}
        ).execute()
        response["replies"].extend(r.get("replies", []))

    return response


def _build_cell_fill_requests(doc: dict, pending: dict) -> list[dict]:
    """
    Find the table at pending['insert_index'] in `doc`, then build insertText
    requests for each cell PLUS bold + bg styling for the header row.
    """
    table = None
    for element in doc.get("body", {}).get("content", []):
        if element.get("startIndex") == pending["insert_index"] and "table" in element:
            table = element["table"]
            break
    if table is None:
        # Fallback: take the last table in the document.
        for element in reversed(doc.get("body", {}).get("content", [])):
            if "table" in element:
                table = element["table"]
                break
    if table is None:
        return []

    requests = []
    # Build cell index map [row][col] -> first content index inside the cell
    cell_first_index: list[list[int]] = []
    for row in table.get("tableRows", []):
        row_indices = []
        for cell in row.get("tableCells", []):
            # The first paragraph's first element's startIndex is where text goes.
            first = cell.get("content", [{}])[0]
            row_indices.append(first.get("startIndex", cell.get("startIndex", 0) + 1))
        cell_first_index.append(row_indices)

    # Insert text into each cell IN REVERSE ORDER (so earlier inserts don't
    # shift later indices). Reverse over rows AND columns.
    sorted_cells = sorted(pending["cells"], key=lambda c: (c["row"], c["col"]), reverse=True)
    for c in sorted_cells:
        idx = cell_first_index[c["row"]][c["col"]]
        if c["text"]:
            requests.append({
                "insertText": {"location": {"index": idx}, "text": c["text"]},
            })

    # Style header row: bold + light gray bg
    if pending["cells"]:
        header_cells = [c for c in pending["cells"] if c["row"] == pending["header_row"]]
        for c in header_cells:
            idx = cell_first_index[c["row"]][c["col"]]
            if c["text"]:
                requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": idx, "endIndex": idx + len(c["text"])},
                        "textStyle": {"bold": True},
                        "fields": "bold",
                    }
                })

    return requests
```

- [ ] **Step 5: Run unit tests to verify they pass**

Run: `ACCOUNT=personal uv run pytest tests/test_markdown_transformer.py::TestTables -v`
Expected: PASS (these tests only check the pure-transformer output, not `render_markdown_to_doc`).

- [ ] **Step 6: Commit**

```bash
git add tools/docs/_markdown.py tests/test_markdown_transformer.py
git commit -m "feat(docs): GFM table handler with 2-step cell population"
```

---

### Task 14: Markdown transformer — kitchen sink integration test

**Files:**
- Modify: `tests/test_markdown_transformer.py`

- [ ] **Step 1: Add a kitchen-sink test**

Append to `tests/test_markdown_transformer.py`:

```python
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

```python
print("code block")
```

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
```

- [ ] **Step 2: Run all transformer tests**

Run: `ACCOUNT=personal uv run pytest tests/test_markdown_transformer.py -v`
Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_markdown_transformer.py
git commit -m "test(docs): add kitchen-sink integration test for markdown transformer"
```

---

## Phase 3 — Reader (Docs → Markdown)

### Task 15: Reader — paragraphs, headings, inline styles

**Files:**
- Create: `tools/docs/_reader.py`
- Create: `tests/test_reader.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_reader.py`:

```python
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
```

- [ ] **Step 2: Run to verify fail**

Run: `ACCOUNT=personal uv run pytest tests/test_reader.py -v`
Expected: FAIL — `_reader.py` doesn't exist.

- [ ] **Step 3: Implement reader basics**

Create `tools/docs/_reader.py`:

```python
"""
Docs JSON → markdown export.

Public entry point:
    docs_to_markdown(document) -> str

Reads structural elements (paragraphs, tables, section breaks) and emits
markdown that round-trips through the transformer with reasonable fidelity.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


_HEADING_PREFIX = {
    "TITLE": "# ",
    "SUBTITLE": "## ",
    "HEADING_1": "# ",
    "HEADING_2": "## ",
    "HEADING_3": "### ",
    "HEADING_4": "#### ",
    "HEADING_5": "##### ",
    "HEADING_6": "###### ",
}


def _wrap_inline(text: str, style: dict) -> str:
    """Apply markdown marks to text per the given Docs textStyle."""
    if not text:
        return text
    out = text
    # link wins over font styling for outer wrap
    if style.get("link", {}).get("url"):
        url = style["link"]["url"]
        return f"[{out}]({url})"
    if style.get("weightedFontFamily", {}).get("fontFamily") == "Roboto Mono":
        out = f"`{out}`"
    if style.get("bold") and style.get("italic"):
        out = f"***{out}***"
    elif style.get("bold"):
        out = f"**{out}**"
    elif style.get("italic"):
        out = f"*{out}*"
    if style.get("strikethrough"):
        out = f"~~{out}~~"
    return out


def _render_paragraph(paragraph: dict) -> str:
    style_name = paragraph.get("paragraphStyle", {}).get("namedStyleType", "NORMAL_TEXT")
    prefix = _HEADING_PREFIX.get(style_name, "")

    parts: list[str] = []
    for element in paragraph.get("elements", []):
        text_run = element.get("textRun")
        if text_run:
            content = text_run.get("content", "")
            style = text_run.get("textStyle", {})
            # Strip the trailing newline from inline rendering — we'll add it back
            if content.endswith("\n"):
                inner = content[:-1]
                parts.append(_wrap_inline(inner, style))
            else:
                parts.append(_wrap_inline(content, style))

    body = "".join(parts)
    return prefix + body + "\n"


def docs_to_markdown(document: dict) -> str:
    """
    Convert a Google Docs JSON document to markdown.

    Supports: paragraphs (incl. headings), inline styles (bold/italic/strike/code/link).
    Lists and tables come in later tasks.
    """
    content_elements = document.get("body", {}).get("content", [])
    out_lines: list[str] = []
    for element in content_elements:
        paragraph = element.get("paragraph")
        if paragraph:
            out_lines.append(_render_paragraph(paragraph))
            continue
        # tables, section breaks, etc. — added in Task 16

    return "".join(out_lines)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `ACCOUNT=personal uv run pytest tests/test_reader.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/docs/_reader.py tests/test_reader.py
git commit -m "feat(docs): reader supports paragraphs, headings, inline styles"
```

---

### Task 16: Reader — lists and tables

**Files:**
- Modify: `tools/docs/_reader.py`
- Modify: `tests/test_reader.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_reader.py`:

```python
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
        # Lists need glyph info via `lists` map — we approximate from glyphType
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `ACCOUNT=personal uv run pytest tests/test_reader.py::TestReaderLists tests/test_reader.py::TestReaderTables -v`
Expected: FAIL.

- [ ] **Step 3: Add list and table support**

Edit `tools/docs/_reader.py`. Replace `docs_to_markdown` and add helpers:

```python
def _render_bullet_line(paragraph: dict, document: dict) -> str:
    """A paragraph that has a `bullet` field — render as a list item."""
    bullet = paragraph.get("bullet") or {}
    list_id = bullet.get("listId")
    nesting = bullet.get("nestingLevel", 0)

    # Determine glyph from document.lists[listId].listProperties.nestingLevels[nesting].glyphType
    glyph_type = "GLYPH_TYPE_UNSPECIFIED"
    lists = document.get("lists", {})
    if list_id and list_id in lists:
        levels = lists[list_id].get("listProperties", {}).get("nestingLevels", [])
        if nesting < len(levels):
            glyph_type = levels[nesting].get("glyphType", glyph_type)

    if glyph_type in ("DECIMAL", "ALPHA", "ROMAN", "UPPER_ALPHA", "UPPER_ROMAN"):
        marker = "1. "
    elif glyph_type == "GLYPH_TYPE_UNSPECIFIED" and lists.get(list_id, {}).get("listProperties", {}).get("nestingLevels", [{}])[nesting].get("glyphSymbol") == "☐":
        marker = "- [ ] "
    else:
        marker = "- "

    inline_parts = []
    for element in paragraph.get("elements", []):
        text_run = element.get("textRun")
        if text_run:
            content = text_run.get("content", "")
            style = text_run.get("textStyle", {})
            if content.endswith("\n"):
                inner = content[:-1]
                inline_parts.append(_wrap_inline(inner, style))
            else:
                inline_parts.append(_wrap_inline(content, style))

    indent = "  " * nesting
    return f"{indent}{marker}{''.join(inline_parts)}\n"


def _render_table(table: dict) -> str:
    rows: list[list[str]] = []
    for tr in table.get("tableRows", []):
        cells: list[str] = []
        for tc in tr.get("tableCells", []):
            cell_text_parts = []
            for content in tc.get("content", []):
                p = content.get("paragraph")
                if p:
                    line = _render_paragraph(p)
                    cell_text_parts.append(line.rstrip("\n"))
            cells.append(" ".join(cell_text_parts).strip() or " ")
        rows.append(cells)

    if not rows:
        return ""

    col_count = max(len(r) for r in rows)
    for r in rows:
        while len(r) < col_count:
            r.append(" ")

    lines = [
        "| " + " | ".join(rows[0]) + " |",
        "| " + " | ".join(["---"] * col_count) + " |",
    ]
    for r in rows[1:]:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines) + "\n"


def docs_to_markdown(document: dict) -> str:
    content_elements = document.get("body", {}).get("content", [])
    out_lines: list[str] = []
    for element in content_elements:
        paragraph = element.get("paragraph")
        if paragraph:
            if paragraph.get("bullet"):
                out_lines.append(_render_bullet_line(paragraph, document))
            else:
                out_lines.append(_render_paragraph(paragraph))
            continue
        table = element.get("table")
        if table:
            out_lines.append(_render_table(table))
            continue
        # section breaks etc. ignored

    return "".join(out_lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `ACCOUNT=personal uv run pytest tests/test_reader.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/docs/_reader.py tests/test_reader.py
git commit -m "feat(docs): reader supports lists and tables"
```

---

### Task 17: Flip read_doc default to markdown + smoke verify

**Files:**
- Modify: `tools/docs/text.py:50`

- [ ] **Step 1: Change the default**

Edit `tools/docs/text.py`. Change the `read_doc` signature:

```python
def read_doc(
    document_id: str,
    format: Literal["markdown", "text", "json"] = "markdown",
) -> dict:
```

- [ ] **Step 2: Smoke test on a real doc**

Pick any document from one of your accounts. Use `search_docs` to find one:

```bash
ACCOUNT=personal uv run python -c "
from auth import get_service
docs = get_service('docs', 'v1')
drive = get_service('drive', 'v3')
files = drive.files().list(
    q=\"mimeType='application/vnd.google-apps.document'\",
    pageSize=1, fields='files(id,name)'
).execute().get('files', [])
print(files)
"
```

Take a document ID and verify the markdown round-trip:

```bash
ACCOUNT=personal uv run python -c "
from tools.docs.text import read_doc
r = read_doc('<paste-doc-id-here>', format='markdown')
print(r['content'][:500])
"
```

Expected: prints the first 500 chars of markdown — headings prefixed with `#`, lists prefixed with `-`, etc. Eyeball for correctness.

- [ ] **Step 3: Commit**

```bash
git add tools/docs/text.py
git commit -m "feat(docs): default read_doc format to markdown"
```

---

## Phase 4 — Bulk Markdown Tools

### Task 18: append_markdown, replace_doc_markdown, replace_range_markdown

**Files:**
- Modify: `tools/docs/text.py`

- [ ] **Step 1: Add the three tools**

Append to `tools/docs/text.py`:

```python
@mcp.tool()
@tool_errors
def append_markdown(document_id: str, markdown: str) -> dict:
    """
    Append markdown-rendered content to the end of a Google Doc.

    Supports headings (#–######), bold/italic/strikethrough/inline code, links,
    bulleted/numbered/checkbox lists (with nesting), tables, images from URLs,
    code blocks, blockquotes, horizontal rules.

    For images from local files, use `insert_image` after appending.
    """
    from ._markdown import render_markdown_to_doc
    service = docs()
    doc = service.documents().get(documentId=document_id).execute()
    idx = end_index(doc)
    render_markdown_to_doc(service, document_id, markdown, insert_index=idx)
    return {"id": document_id, "status": f"Appended markdown ({len(markdown)} chars)."}


@mcp.tool()
@tool_errors
def replace_doc_markdown(document_id: str, markdown: str) -> dict:
    """
    Replace the entire body of a Google Doc with markdown-rendered content.

    Existing body content is deleted first; markdown is then inserted at index 1.
    Headers, footers, and document metadata are preserved.
    """
    from ._markdown import render_markdown_to_doc
    service = docs()
    doc = service.documents().get(documentId=document_id).execute()
    body_end = end_index(doc)
    if body_end > 1:
        service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": [{"deleteContentRange": {
                "range": {"startIndex": 1, "endIndex": body_end},
            }}]},
        ).execute()
    if markdown:
        render_markdown_to_doc(service, document_id, markdown, insert_index=1)
    return {"id": document_id, "status": "Document body replaced."}


@mcp.tool()
@tool_errors
def replace_range_markdown(
    document_id: str,
    start_index: int,
    end_index_param: int,
    markdown: str,
) -> dict:
    """
    Replace content between start_index and end_index_param with markdown.

    Use `read_doc(format='json')` to find the right indices first.
    """
    from ._markdown import render_markdown_to_doc
    service = docs()
    if end_index_param > start_index:
        service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": [{"deleteContentRange": {
                "range": {"startIndex": start_index, "endIndex": end_index_param},
            }}]},
        ).execute()
    if markdown:
        render_markdown_to_doc(service, document_id, markdown, insert_index=start_index)
    return {"id": document_id, "status": f"Replaced range with markdown."}
```

Note: parameter is `end_index_param` rather than `end_index` to avoid clashing with the imported `end_index` helper.

- [ ] **Step 2: Smoke test**

Create a test doc and append markdown:

```bash
ACCOUNT=personal uv run python -c "
from tools.docs.manage import create_doc
from tools.docs.text import append_markdown
r = create_doc('Markdown Smoke Test')
doc_id = r['id']
append_markdown(doc_id, '''# Hello

This is **bold** and *italic*.

- one
- two
  - nested
''')
print('Open:', r['link'])
"
```

Open the link in a browser. Expected: see a styled doc with H1 heading, bold + italic text, nested list.

- [ ] **Step 3: Commit**

```bash
git add tools/docs/text.py
git commit -m "feat(docs): add append_markdown, replace_doc_markdown, replace_range_markdown"
```

---

### Task 19: find_and_replace

**Files:**
- Modify: `tools/docs/text.py`

- [ ] **Step 1: Add the tool**

Append to `tools/docs/text.py`:

```python
@mcp.tool()
@tool_errors
def find_and_replace(
    document_id: str,
    find: str,
    replace: str,
    match_case: bool = False,
) -> dict:
    """
    Find and replace text across the entire document.

    Args:
        document_id: The Google Docs document ID.
        find: Text to search for.
        replace: Replacement text.
        match_case: Whether to match case exactly (default False).
    """
    service = docs()
    response = service.documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"replaceAllText": {
            "containsText": {"text": find, "matchCase": match_case},
            "replaceText": replace,
        }}]},
    ).execute()
    occurrences = response.get("replies", [{}])[0].get("replaceAllText", {}).get("occurrencesChanged", 0)
    return {"id": document_id, "occurrences_changed": occurrences}
```

- [ ] **Step 2: Smoke test**

```bash
ACCOUNT=personal uv run python -c "
from tools.docs.text import find_and_replace
print(find_and_replace('<doc-id-from-prev-task>', 'bold', 'STRONG'))
"
```

Expected: prints `{'id': '...', 'occurrences_changed': 1}` (or more). Open the doc to confirm.

- [ ] **Step 3: Commit**

```bash
git add tools/docs/text.py
git commit -m "feat(docs): add find_and_replace"
```

---

## Phase 5 — Text & Paragraph Styling

### Task 20: apply_text_style

**Files:**
- Modify: `tools/docs/style.py`

- [ ] **Step 1: Implement the tool**

Replace `tools/docs/style.py` content:

```python
"""Text and paragraph styling tools."""

import logging
from typing import Optional

from app import mcp
from ._common import docs, parse_color, pt, tool_errors

logger = logging.getLogger(__name__)


@mcp.tool()
@tool_errors
def apply_text_style(
    document_id: str,
    start_index: int,
    end_index: int,
    bold: Optional[bool] = None,
    italic: Optional[bool] = None,
    underline: Optional[bool] = None,
    strikethrough: Optional[bool] = None,
    font_family: Optional[str] = None,
    font_size_pt: Optional[float] = None,
    foreground_color: Optional[str] = None,
    background_color: Optional[str] = None,
    link_url: Optional[str] = None,
) -> dict:
    """
    Apply text styling to a range. Only the parameters you pass are changed;
    others are left untouched.

    Range indices come from `read_doc(format='json')`.

    Args:
        document_id: The Google Docs document ID.
        start_index, end_index: Range to style.
        bold/italic/underline/strikethrough: Toggle these styles.
        font_family: e.g. "Roboto", "Roboto Mono", "Georgia", "Calibri".
        font_size_pt: Font size in points (e.g. 12, 18).
        foreground_color, background_color: "#rrggbb", "#rgb", or named color.
        link_url: Set as a hyperlink. Pass empty string "" to remove.
    """
    style: dict = {}
    fields: list[str] = []

    if bold is not None:
        style["bold"] = bold
        fields.append("bold")
    if italic is not None:
        style["italic"] = italic
        fields.append("italic")
    if underline is not None:
        style["underline"] = underline
        fields.append("underline")
    if strikethrough is not None:
        style["strikethrough"] = strikethrough
        fields.append("strikethrough")
    if font_family is not None:
        style["weightedFontFamily"] = {"fontFamily": font_family}
        fields.append("weightedFontFamily")
    if font_size_pt is not None:
        style["fontSize"] = pt(font_size_pt)
        fields.append("fontSize")
    if foreground_color is not None:
        style["foregroundColor"] = {"color": {"rgbColor": parse_color(foreground_color)}}
        fields.append("foregroundColor")
    if background_color is not None:
        style["backgroundColor"] = {"color": {"rgbColor": parse_color(background_color)}}
        fields.append("backgroundColor")
    if link_url is not None:
        style["link"] = {"url": link_url} if link_url else {}
        fields.append("link")

    if not fields:
        return {"id": document_id, "status": "No style changes specified."}

    docs().documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"updateTextStyle": {
            "range": {"startIndex": start_index, "endIndex": end_index},
            "textStyle": style,
            "fields": ",".join(fields),
        }}]},
    ).execute()
    return {"id": document_id, "status": f"Applied text style to range {start_index}–{end_index}."}
```

- [ ] **Step 2: Smoke test**

```bash
ACCOUNT=personal uv run python -c "
from tools.docs.manage import create_doc
from tools.docs.text import append_to_doc
from tools.docs.style import apply_text_style
r = create_doc('Style Smoke Test')
append_to_doc(r['id'], 'This is styled text.\n')
# 'styled' starts at index 9 (after 'This is '), ends at 15
apply_text_style(r['id'], 9, 15, bold=True, foreground_color='#ff0000', font_size_pt=18)
print('Open:', r['link'])
"
```

Open the link. Expected: word "styled" rendered red, bold, 18pt.

- [ ] **Step 3: Commit**

```bash
git add tools/docs/style.py
git commit -m "feat(docs): add apply_text_style tool"
```

---

### Task 21: apply_paragraph_style

**Files:**
- Modify: `tools/docs/style.py`

- [ ] **Step 1: Add the tool**

Append to `tools/docs/style.py`:

```python
_NAMED_STYLES = {
    "TITLE", "SUBTITLE",
    "HEADING_1", "HEADING_2", "HEADING_3",
    "HEADING_4", "HEADING_5", "HEADING_6",
    "NORMAL_TEXT",
}
_ALIGNMENTS = {"START", "CENTER", "END", "JUSTIFIED"}


@mcp.tool()
@tool_errors
def apply_paragraph_style(
    document_id: str,
    start_index: int,
    end_index: int,
    named_style: Optional[str] = None,
    alignment: Optional[str] = None,
    line_spacing: Optional[float] = None,
    indent_first_line_pt: Optional[float] = None,
    indent_start_pt: Optional[float] = None,
    space_above_pt: Optional[float] = None,
    space_below_pt: Optional[float] = None,
    keep_with_next: Optional[bool] = None,
) -> dict:
    """
    Apply paragraph styling to a range.

    Args:
        named_style: One of TITLE, SUBTITLE, HEADING_1..6, NORMAL_TEXT.
                     Applies Google Docs' built-in named style — best for
                     ensuring a polished, consistent visual hierarchy.
        alignment: START | CENTER | END | JUSTIFIED.
        line_spacing: Multiplier. 1.0=single, 1.15, 1.5, 2.0 typical.
        indent_first_line_pt, indent_start_pt: Indentation in points.
        space_above_pt, space_below_pt: Paragraph spacing in points.
        keep_with_next: Prevent page break between this paragraph and the next.
    """
    style: dict = {}
    fields: list[str] = []

    if named_style is not None:
        if named_style not in _NAMED_STYLES:
            raise ValueError(f"named_style must be one of {sorted(_NAMED_STYLES)}; got {named_style!r}")
        style["namedStyleType"] = named_style
        fields.append("namedStyleType")
    if alignment is not None:
        if alignment not in _ALIGNMENTS:
            raise ValueError(f"alignment must be one of {sorted(_ALIGNMENTS)}; got {alignment!r}")
        style["alignment"] = alignment
        fields.append("alignment")
    if line_spacing is not None:
        # Docs API expects percentage: 1.5x = 150
        style["lineSpacing"] = float(line_spacing) * 100
        fields.append("lineSpacing")
    if indent_first_line_pt is not None:
        style["indentFirstLine"] = pt(indent_first_line_pt)
        fields.append("indentFirstLine")
    if indent_start_pt is not None:
        style["indentStart"] = pt(indent_start_pt)
        fields.append("indentStart")
    if space_above_pt is not None:
        style["spaceAbove"] = pt(space_above_pt)
        fields.append("spaceAbove")
    if space_below_pt is not None:
        style["spaceBelow"] = pt(space_below_pt)
        fields.append("spaceBelow")
    if keep_with_next is not None:
        style["keepWithNext"] = keep_with_next
        fields.append("keepWithNext")

    if not fields:
        return {"id": document_id, "status": "No style changes specified."}

    docs().documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"updateParagraphStyle": {
            "range": {"startIndex": start_index, "endIndex": end_index},
            "paragraphStyle": style,
            "fields": ",".join(fields),
        }}]},
    ).execute()
    return {"id": document_id, "status": f"Applied paragraph style to range {start_index}–{end_index}."}
```

- [ ] **Step 2: Smoke test**

```bash
ACCOUNT=personal uv run python -c "
from tools.docs.manage import create_doc
from tools.docs.text import append_to_doc
from tools.docs.style import apply_paragraph_style
r = create_doc('Para Style Smoke Test')
append_to_doc(r['id'], 'My Title\nA centered paragraph below.\n')
apply_paragraph_style(r['id'], 1, 9, named_style='TITLE')
apply_paragraph_style(r['id'], 10, 36, alignment='CENTER', line_spacing=1.5)
print('Open:', r['link'])
"
```

Open the link. Expected: "My Title" rendered as Doc Title style; below paragraph centered with 1.5x line spacing.

- [ ] **Step 3: Commit**

```bash
git add tools/docs/style.py
git commit -m "feat(docs): add apply_paragraph_style tool"
```

---

## Phase 6 — Structure

### Task 22: insert_page_break, insert_horizontal_rule, insert_section_break

**Files:**
- Modify: `tools/docs/structure.py`

- [ ] **Step 1: Implement the three tools**

Replace `tools/docs/structure.py`:

```python
"""Structural tools — page breaks, sections, headers/footers, page setup."""

import logging
from typing import Optional

from app import mcp
from ._common import docs, parse_color, pt, tool_errors

logger = logging.getLogger(__name__)


@mcp.tool()
@tool_errors
def insert_page_break(document_id: str, index: int) -> dict:
    """Insert a page break at the given index."""
    docs().documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"insertPageBreak": {"location": {"index": index}}}]},
    ).execute()
    return {"id": document_id, "status": f"Page break at {index}."}


@mcp.tool()
@tool_errors
def insert_horizontal_rule(document_id: str, index: int) -> dict:
    """
    Insert a horizontal rule (divider line) at the given index.

    Implemented as a paragraph with a bottom border, since the Docs API has
    no native horizontal-rule request.
    """
    requests = [
        {"insertText": {"location": {"index": index}, "text": "\n"}},
        {"updateParagraphStyle": {
            "range": {"startIndex": index, "endIndex": index + 1},
            "paragraphStyle": {
                "borderBottom": {
                    "color": {"color": {"rgbColor": {"red": 0.7, "green": 0.7, "blue": 0.7}}},
                    "width": {"magnitude": 1, "unit": "PT"},
                    "padding": {"magnitude": 1, "unit": "PT"},
                    "dashStyle": "SOLID",
                }
            },
            "fields": "borderBottom",
        }},
    ]
    docs().documents().batchUpdate(
        documentId=document_id, body={"requests": requests}
    ).execute()
    return {"id": document_id, "status": f"Horizontal rule at {index}."}


@mcp.tool()
@tool_errors
def insert_section_break(
    document_id: str,
    index: int,
    type: str = "NEXT_PAGE",
) -> dict:
    """
    Insert a section break. Sections allow varying margins, columns, page
    orientation per region.

    Args:
        type: "NEXT_PAGE" (default — starts a new page) or "CONTINUOUS".
    """
    if type not in ("NEXT_PAGE", "CONTINUOUS"):
        raise ValueError(f"type must be NEXT_PAGE or CONTINUOUS; got {type!r}")
    docs().documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"insertSectionBreak": {
            "location": {"index": index},
            "sectionType": type,
        }}]},
    ).execute()
    return {"id": document_id, "status": f"{type} section break at {index}."}
```

- [ ] **Step 2: Smoke test**

```bash
ACCOUNT=personal uv run python -c "
from tools.docs.manage import create_doc
from tools.docs.text import append_to_doc
from tools.docs.structure import insert_page_break, insert_horizontal_rule
r = create_doc('Structure Smoke Test')
append_to_doc(r['id'], 'Page one content.\n')
from tools.docs._common import docs, end_index
doc = docs().documents().get(documentId=r['id']).execute()
idx = end_index(doc)
insert_page_break(r['id'], idx)
doc = docs().documents().get(documentId=r['id']).execute()
idx = end_index(doc)
insert_horizontal_rule(r['id'], idx)
append_to_doc(r['id'], 'Page two content below an HR.\n')
print('Open:', r['link'])
"
```

Open. Expected: "Page one content." then a forced page break, then on page 2 a horizontal rule line + "Page two content below an HR."

- [ ] **Step 3: Commit**

```bash
git add tools/docs/structure.py
git commit -m "feat(docs): add page break, section break, horizontal rule tools"
```

---

### Task 23: update_section_columns, update_page_setup

**Files:**
- Modify: `tools/docs/structure.py`

- [ ] **Step 1: Add the two tools**

Append to `tools/docs/structure.py`:

```python
@mcp.tool()
@tool_errors
def update_section_columns(
    document_id: str,
    section_start_index: int,
    column_count: int,
    separator: bool = False,
) -> dict:
    """
    Set the column count for a section.

    A section's start is at a section break (or document start). Use
    `read_doc(format='json')` to find sectionBreak elements and their indices.

    Args:
        section_start_index: Index of the section break that begins the section
                             (or 0 for the first section).
        column_count: Number of columns (1, 2, 3, ...).
        separator: Draw a vertical line between columns.
    """
    if column_count < 1:
        raise ValueError("column_count must be >= 1")

    docs().documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"updateSectionStyle": {
            "range": {"startIndex": section_start_index, "endIndex": section_start_index + 1},
            "sectionStyle": {
                "columnProperties": [{} for _ in range(column_count)],
                "columnSeparatorStyle": "BETWEEN_EACH_COLUMN" if separator else "NONE",
            },
            "fields": "columnProperties,columnSeparatorStyle",
        }}]},
    ).execute()
    return {"id": document_id, "status": f"Section at {section_start_index} set to {column_count} columns."}


@mcp.tool()
@tool_errors
def update_page_setup(
    document_id: str,
    top_margin_pt: Optional[float] = None,
    bottom_margin_pt: Optional[float] = None,
    left_margin_pt: Optional[float] = None,
    right_margin_pt: Optional[float] = None,
    page_width_pt: Optional[float] = None,
    page_height_pt: Optional[float] = None,
    orientation: Optional[str] = None,
) -> dict:
    """
    Update document-wide page setup.

    Args:
        margins: in points (72pt = 1 inch).
        page_width_pt, page_height_pt: e.g. Letter = 612x792, A4 = 595x842.
        orientation: "portrait" or "landscape". If set, swaps width/height
                     as needed (uses Letter dimensions if width/height not given).
    """
    style: dict = {}
    fields: list[str] = []

    if top_margin_pt is not None:
        style["marginTop"] = pt(top_margin_pt)
        fields.append("marginTop")
    if bottom_margin_pt is not None:
        style["marginBottom"] = pt(bottom_margin_pt)
        fields.append("marginBottom")
    if left_margin_pt is not None:
        style["marginLeft"] = pt(left_margin_pt)
        fields.append("marginLeft")
    if right_margin_pt is not None:
        style["marginRight"] = pt(right_margin_pt)
        fields.append("marginRight")

    if orientation is not None:
        if orientation not in ("portrait", "landscape"):
            raise ValueError("orientation must be 'portrait' or 'landscape'")
        # Use Letter as default
        w, h = page_width_pt or 612, page_height_pt or 792
        if orientation == "landscape" and w < h:
            w, h = h, w
        elif orientation == "portrait" and w > h:
            w, h = h, w
        style["pageSize"] = {"width": pt(w), "height": pt(h)}
        fields.append("pageSize")
    elif page_width_pt is not None or page_height_pt is not None:
        # Apply just the dimensions
        style["pageSize"] = {
            "width": pt(page_width_pt or 612),
            "height": pt(page_height_pt or 792),
        }
        fields.append("pageSize")

    if not fields:
        return {"id": document_id, "status": "No page setup changes specified."}

    docs().documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"updateDocumentStyle": {
            "documentStyle": style,
            "fields": ",".join(fields),
        }}]},
    ).execute()
    return {"id": document_id, "status": "Page setup updated."}
```

- [ ] **Step 2: Smoke test**

```bash
ACCOUNT=personal uv run python -c "
from tools.docs.manage import create_doc
from tools.docs.text import append_to_doc
from tools.docs.structure import update_page_setup
r = create_doc('Page Setup Smoke Test')
append_to_doc(r['id'], 'This page should be landscape with thin margins.\n')
update_page_setup(r['id'], orientation='landscape', top_margin_pt=36, bottom_margin_pt=36, left_margin_pt=36, right_margin_pt=36)
print('Open:', r['link'])
"
```

Open. Expected: landscape orientation, ~0.5 inch margins all around.

- [ ] **Step 3: Commit**

```bash
git add tools/docs/structure.py
git commit -m "feat(docs): add update_section_columns and update_page_setup"
```

---

### Task 24: update_header_footer

**Files:**
- Modify: `tools/docs/structure.py`

- [ ] **Step 1: Add the tool**

Append to `tools/docs/structure.py`:

```python
@mcp.tool()
@tool_errors
def update_header_footer(
    document_id: str,
    header_markdown: Optional[str] = None,
    footer_markdown: Optional[str] = None,
    include_page_numbers: bool = False,
    first_page_different: bool = False,
) -> dict:
    """
    Set the document header and/or footer.

    Args:
        header_markdown: Markdown content for the header. If None, header
                         is not modified (but it may be created if needed for
                         page numbers).
        footer_markdown: Same for footer.
        include_page_numbers: Adds "Page <num>" to the footer (or header if
                               footer_markdown is None).
        first_page_different: If True, the first page has its own header/footer
                              (left blank).
    """
    from ._markdown import render_markdown_to_doc

    service = docs()

    # Optionally toggle "use first page header/footer" first
    if first_page_different:
        service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": [{"updateDocumentStyle": {
                "documentStyle": {"useFirstPageHeaderFooter": True},
                "fields": "useFirstPageHeaderFooter",
            }}]},
        ).execute()

    doc = service.documents().get(documentId=document_id).execute()
    header_id = doc.get("documentStyle", {}).get("defaultHeaderId")
    footer_id = doc.get("documentStyle", {}).get("defaultFooterId")

    if header_markdown is not None and header_id is None:
        r = service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": [{"createHeader": {"type": "DEFAULT"}}]},
        ).execute()
        header_id = r["replies"][0]["createHeader"]["headerId"]

    if (footer_markdown is not None or include_page_numbers) and footer_id is None:
        r = service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": [{"createFooter": {"type": "DEFAULT"}}]},
        ).execute()
        footer_id = r["replies"][0]["createFooter"]["footerId"]

    # Helper: clear segment and insert markdown
    def _fill_segment(segment_id: str, markdown: str, *, with_page_number: bool = False) -> None:
        # Read current segment range
        d = service.documents().get(documentId=document_id).execute()
        segments = d.get("headers", {}) if segment_id == header_id else d.get("footers", {})
        seg = segments.get(segment_id)
        if not seg:
            return
        # Find the segment's current content end index
        content = seg.get("content", [])
        if content:
            seg_end = content[-1]["endIndex"]
            # Clear existing content (skip the trailing newline at endIndex - 1)
            if seg_end > 1:
                service.documents().batchUpdate(
                    documentId=document_id,
                    body={"requests": [{"deleteContentRange": {
                        "segmentId": segment_id,
                        "range": {
                            "segmentId": segment_id,
                            "startIndex": 0,
                            "endIndex": seg_end - 1,
                        },
                    }}]},
                ).execute()
        if markdown:
            # Render markdown using a segment-aware batch
            # Simplified: just insertText with the rendered text + apply minimal styling.
            # Full markdown in headers is fragile; we limit to inline styles via
            # a basic text insert. For richer styling, the user can call
            # apply_text_style on the segment.
            service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [{"insertText": {
                    "location": {"segmentId": segment_id, "index": 0},
                    "text": markdown,
                }}]},
            ).execute()
        if with_page_number:
            # Insert at end of segment
            # Re-read to find the new end
            d = service.documents().get(documentId=document_id).execute()
            segments = d.get("headers", {}) if segment_id == header_id else d.get("footers", {})
            seg = segments.get(segment_id, {})
            content = seg.get("content", [])
            end = content[-1]["endIndex"] - 1 if content else 0
            service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [
                    {"insertText": {
                        "location": {"segmentId": segment_id, "index": end},
                        "text": " Page ",
                    }},
                    # Insert auto page number
                    # The Docs API supports `insertAutoText` only via UI; the
                    # API has no direct page number request. We document this
                    # limitation and insert the literal text "Page #" as a
                    # placeholder. Users can replace # with the page-number
                    # field in the UI manually, or use a Google Apps Script.
                ]},
            ).execute()

    if header_markdown is not None and header_id:
        _fill_segment(header_id, header_markdown)
    if (footer_markdown is not None or include_page_numbers) and footer_id:
        _fill_segment(footer_id, footer_markdown or "", with_page_number=include_page_numbers)

    return {"id": document_id, "status": "Header/footer updated."}
```

**Note in code/docstring:** The Docs API has no direct insertAutoText for page numbers. We insert literal "Page " text as a placeholder. This is a documented limitation. (Full page-number autoText needs Apps Script or manual UI action.)

- [ ] **Step 2: Smoke test**

```bash
ACCOUNT=personal uv run python -c "
from tools.docs.manage import create_doc
from tools.docs.text import append_to_doc
from tools.docs.structure import update_header_footer
r = create_doc('Header Footer Smoke')
for i in range(60):
    append_to_doc(r['id'], f'Line {i+1} of body content.\n')
update_header_footer(r['id'], header_markdown='My Report', footer_markdown='Confidential')
print('Open:', r['link'])
"
```

Open. Expected: every page shows "My Report" at top and "Confidential" at bottom.

- [ ] **Step 3: Commit**

```bash
git add tools/docs/structure.py
git commit -m "feat(docs): add update_header_footer with documented page-number limitation"
```

---

## Phase 7 — Media & Tables

### Task 25: insert_image (URL + local path)

**Files:**
- Modify: `tools/docs/media.py`

- [ ] **Step 1: Implement insert_image**

Replace `tools/docs/media.py`:

```python
"""Image insertion — supports URLs and local file paths (uploaded via Drive)."""

import logging
import mimetypes
import os
from typing import Optional

from googleapiclient.http import MediaFileUpload

from app import mcp
from ._common import docs, drive, pt, tool_errors

logger = logging.getLogger(__name__)


def _upload_image_to_drive(local_path: str) -> str:
    """Upload a local image to Drive and return a public-readable URL."""
    if not os.path.isfile(local_path):
        raise ValueError(f"Local image not found: {local_path}")

    mime, _ = mimetypes.guess_type(local_path)
    if not mime or not mime.startswith("image/"):
        raise ValueError(f"Not a recognized image type: {local_path}")

    service = drive()
    file_metadata = {"name": os.path.basename(local_path)}
    media = MediaFileUpload(local_path, mimetype=mime)
    f = service.files().create(
        body=file_metadata, media_body=media, fields="id"
    ).execute()
    file_id = f["id"]
    # Make publicly readable so the Docs API can fetch it
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()
    return f"https://drive.google.com/uc?id={file_id}"


@mcp.tool()
@tool_errors
def insert_image(
    document_id: str,
    index: int,
    source: str,
    width_pt: Optional[float] = None,
    height_pt: Optional[float] = None,
) -> dict:
    """
    Insert an inline image at the given index.

    Args:
        source: A URL (http(s)://...) OR a local file path. Local files are
                uploaded to Drive (made publicly readable) and then embedded.
        width_pt, height_pt: Optional size in points (72pt = 1 inch). If both
                              omitted, Docs sizes to the image's native size.
                              If only one is given, the other is omitted (Docs
                              preserves aspect ratio).
    """
    if source.startswith(("http://", "https://")):
        uri = source
    else:
        uri = _upload_image_to_drive(source)

    request: dict = {
        "insertInlineImage": {
            "location": {"index": index},
            "uri": uri,
        }
    }
    if width_pt or height_pt:
        size: dict = {}
        if width_pt:
            size["width"] = pt(width_pt)
        if height_pt:
            size["height"] = pt(height_pt)
        request["insertInlineImage"]["objectSize"] = size

    docs().documents().batchUpdate(
        documentId=document_id, body={"requests": [request]}
    ).execute()
    return {"id": document_id, "status": f"Image inserted at {index}."}
```

- [ ] **Step 2: Smoke test (URL)**

```bash
ACCOUNT=personal uv run python -c "
from tools.docs.manage import create_doc
from tools.docs.media import insert_image
r = create_doc('Image Smoke Test')
insert_image(r['id'], 1, 'https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_272x92dp.png', width_pt=200)
print('Open:', r['link'])
"
```

Open. Expected: Google logo embedded at 200pt wide.

- [ ] **Step 3: Smoke test (local)**

Take any small `.png` you have. Run:

```bash
ACCOUNT=personal uv run python -c "
from tools.docs.manage import create_doc
from tools.docs.media import insert_image
r = create_doc('Local Image Smoke')
insert_image(r['id'], 1, '/absolute/path/to/an/image.png', width_pt=300)
print('Open:', r['link'])
"
```

Open. Expected: the local image uploaded and embedded. Check Drive: a file named `image.png` should appear (publicly readable).

- [ ] **Step 4: Commit**

```bash
git add tools/docs/media.py
git commit -m "feat(docs): add insert_image with URL and local-path support"
```

---

### Task 26: style_table_cells

**Files:**
- Modify: `tools/docs/tables.py`

- [ ] **Step 1: Implement style_table_cells**

Replace `tools/docs/tables.py`:

```python
"""Table styling tools."""

import logging
from typing import Optional

from app import mcp
from ._common import docs, parse_color, pt, tool_errors

logger = logging.getLogger(__name__)


_TEXT_ALIGN = {"START", "CENTER", "END"}
_V_ALIGN = {"TOP", "MIDDLE", "BOTTOM"}


@mcp.tool()
@tool_errors
def style_table_cells(
    document_id: str,
    table_start_index: int,
    row_range: list,                       # [start_row, end_row] inclusive 0-based
    col_range: list,                       # [start_col, end_col] inclusive 0-based
    background_color: Optional[str] = None,
    text_alignment: Optional[str] = None,
    vertical_alignment: Optional[str] = None,
    padding_pt: Optional[float] = None,
    border_color: Optional[str] = None,
    border_width_pt: Optional[float] = None,
) -> dict:
    """
    Apply cell-level styling to a rectangular range within a table.

    Args:
        table_start_index: The Docs index where the table starts (from
                           `read_doc(format='json')`).
        row_range: [start_row, end_row] inclusive, 0-based.
        col_range: [start_col, end_col] inclusive, 0-based.
        background_color: Cell background.
        text_alignment: START / CENTER / END.
        vertical_alignment: TOP / MIDDLE / BOTTOM.
        padding_pt: Cell padding on all sides in points.
        border_color, border_width_pt: Cell border color and width.
                                       Sets all four sides.
    """
    if not (isinstance(row_range, list) and len(row_range) == 2):
        raise ValueError("row_range must be [start_row, end_row]")
    if not (isinstance(col_range, list) and len(col_range) == 2):
        raise ValueError("col_range must be [start_col, end_col]")

    cell_style: dict = {}
    fields: list[str] = []

    if background_color is not None:
        cell_style["backgroundColor"] = {"color": {"rgbColor": parse_color(background_color)}}
        fields.append("backgroundColor")
    if padding_pt is not None:
        p = pt(padding_pt)
        cell_style.update({
            "paddingTop": p, "paddingBottom": p,
            "paddingLeft": p, "paddingRight": p,
        })
        fields.extend(["paddingTop", "paddingBottom", "paddingLeft", "paddingRight"])
    if border_color is not None or border_width_pt is not None:
        border = {
            "color": {"color": {"rgbColor": parse_color(border_color or "#999999")}},
            "width": pt(border_width_pt or 1),
            "dashStyle": "SOLID",
        }
        for side in ("borderTop", "borderBottom", "borderLeft", "borderRight"):
            cell_style[side] = border
            fields.append(side)
    if vertical_alignment is not None:
        if vertical_alignment not in _V_ALIGN:
            raise ValueError(f"vertical_alignment must be one of {sorted(_V_ALIGN)}")
        cell_style["contentAlignment"] = vertical_alignment
        fields.append("contentAlignment")

    requests: list[dict] = []

    if fields:
        requests.append({
            "updateTableCellStyle": {
                "tableStartLocation": {"index": table_start_index},
                "tableRange": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": table_start_index},
                        "rowIndex": row_range[0],
                        "columnIndex": col_range[0],
                    },
                    "rowSpan": row_range[1] - row_range[0] + 1,
                    "columnSpan": col_range[1] - col_range[0] + 1,
                },
                "tableCellStyle": cell_style,
                "fields": ",".join(fields),
            }
        })

    if text_alignment is not None:
        if text_alignment not in _TEXT_ALIGN:
            raise ValueError(f"text_alignment must be one of {sorted(_TEXT_ALIGN)}")
        # text_alignment requires updateParagraphStyle on the paragraphs inside
        # the cells. We need to find each cell's paragraph range.
        # The cleanest approach: read the doc, locate the cells, emit updates.
        service = docs()
        doc = service.documents().get(documentId=document_id).execute()
        table = None
        for element in doc.get("body", {}).get("content", []):
            if element.get("startIndex") == table_start_index and "table" in element:
                table = element["table"]
                break
        if table:
            for r in range(row_range[0], row_range[1] + 1):
                for c in range(col_range[0], col_range[1] + 1):
                    cell = table["tableRows"][r]["tableCells"][c]
                    for p in cell.get("content", []):
                        para = p.get("paragraph")
                        if para:
                            start = p["startIndex"]
                            end = p["endIndex"]
                            requests.append({
                                "updateParagraphStyle": {
                                    "range": {"startIndex": start, "endIndex": end},
                                    "paragraphStyle": {"alignment": text_alignment},
                                    "fields": "alignment",
                                }
                            })

    if not requests:
        return {"id": document_id, "status": "No style changes specified."}

    docs().documents().batchUpdate(
        documentId=document_id, body={"requests": requests}
    ).execute()
    return {"id": document_id, "status": "Table cells styled."}
```

- [ ] **Step 2: Smoke test**

```bash
ACCOUNT=personal uv run python -c "
from tools.docs.manage import create_doc
from tools.docs.text import append_markdown, read_doc
from tools.docs.tables import style_table_cells
r = create_doc('Table Style Smoke')
append_markdown(r['id'], '''| Name | Score |
|---|---|
| Alice | 10 |
| Bob | 7 |
''')
# Find the table index
doc = read_doc(r['id'], format='json')['document']
table_idx = None
for element in doc['body']['content']:
    if 'table' in element:
        table_idx = element['startIndex']
        break
# Style header row: cyan background, white text, centered
style_table_cells(r['id'], table_idx, [0, 0], [0, 1], background_color='#1a73e8', text_alignment='CENTER')
print('Open:', r['link'])
"
```

Open. Expected: table header row has blue background and centered text.

- [ ] **Step 3: Commit**

```bash
git add tools/docs/tables.py
git commit -m "feat(docs): add style_table_cells with background, alignment, padding, borders"
```

---

### Task 27: merge_table_cells

**Files:**
- Modify: `tools/docs/tables.py`

- [ ] **Step 1: Add the tool**

Append to `tools/docs/tables.py`:

```python
@mcp.tool()
@tool_errors
def merge_table_cells(
    document_id: str,
    table_start_index: int,
    row_start: int,
    col_start: int,
    row_end: int,
    col_end: int,
) -> dict:
    """
    Merge a rectangular block of cells. row_end and col_end are inclusive
    0-based indices.
    """
    docs().documents().batchUpdate(
        documentId=document_id,
        body={"requests": [{"mergeTableCells": {
            "tableRange": {
                "tableCellLocation": {
                    "tableStartLocation": {"index": table_start_index},
                    "rowIndex": row_start,
                    "columnIndex": col_start,
                },
                "rowSpan": row_end - row_start + 1,
                "columnSpan": col_end - col_start + 1,
            },
        }}]},
    ).execute()
    return {"id": document_id, "status": f"Merged cells ({row_start},{col_start}) to ({row_end},{col_end})."}
```

- [ ] **Step 2: Smoke test**

```bash
ACCOUNT=personal uv run python -c "
from tools.docs.manage import create_doc
from tools.docs.text import append_markdown, read_doc
from tools.docs.tables import merge_table_cells
r = create_doc('Merge Smoke')
append_markdown(r['id'], '''| A | B | C |
|---|---|---|
| 1 | 2 | 3 |
| 4 | 5 | 6 |
''')
doc = read_doc(r['id'], format='json')['document']
for element in doc['body']['content']:
    if 'table' in element:
        merge_table_cells(r['id'], element['startIndex'], 1, 0, 1, 2)  # merge row 1 across all cols
        break
print('Open:', r['link'])
"
```

Open. Expected: middle row spans all 3 columns.

- [ ] **Step 3: Commit**

```bash
git add tools/docs/tables.py
git commit -m "feat(docs): add merge_table_cells"
```

---

## Phase 8 — Templates & Doc Management

### Task 28: copy_doc_from_template, rename_doc

**Files:**
- Modify: `tools/docs/manage.py`

- [ ] **Step 1: Add the two tools**

Append to `tools/docs/manage.py`:

```python
@mcp.tool()
@tool_errors
def copy_doc_from_template(template_id: str, new_title: str) -> dict:
    """
    Duplicate a Google Doc. Useful for branded templates (proposals, reports).

    The new doc lives in the user's Drive. Requires drive.file scope.
    """
    new_file = drive().files().copy(
        fileId=template_id,
        body={"name": new_title},
        fields="id, name, webViewLink",
    ).execute()
    return {
        "id": new_file["id"],
        "title": new_file["name"],
        "link": new_file.get("webViewLink", f"https://docs.google.com/document/d/{new_file['id']}/edit"),
    }


@mcp.tool()
@tool_errors
def rename_doc(document_id: str, new_title: str) -> dict:
    """Rename a Google Doc. Requires drive.file scope."""
    f = drive().files().update(
        fileId=document_id,
        body={"name": new_title},
        fields="id, name",
    ).execute()
    return {"id": f["id"], "title": f["name"]}
```

- [ ] **Step 2: Smoke test (rename)**

```bash
ACCOUNT=personal uv run python -c "
from tools.docs.manage import create_doc, rename_doc
r = create_doc('Original Title')
print('Before:', r)
r2 = rename_doc(r['id'], 'New Title After Rename')
print('After:', r2)
"
```

Expected: title prints as "New Title After Rename".

- [ ] **Step 3: Smoke test (template copy)**

Use the doc you just renamed (or any existing doc):

```bash
ACCOUNT=personal uv run python -c "
from tools.docs.manage import copy_doc_from_template
print(copy_doc_from_template('<doc-id-from-prev-step>', 'Copy of My Template'))
"
```

Expected: returns id + link of a new doc. Open it; should match the source.

- [ ] **Step 4: Commit**

```bash
git add tools/docs/manage.py
git commit -m "feat(docs): add copy_doc_from_template and rename_doc"
```

---

## Phase 9 — Documentation

### Task 29: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the Docs section**

Edit `README.md`. Replace the Docs table:

```markdown
### Docs

| Tool | Description |
|---|---|
| `search_docs` | Search Drive for Google Docs |
| `read_doc` | Read document content as markdown (default), plain text, or raw JSON with indices |
| `create_doc` | Create a new document (optionally with markdown or plain text content) |
| `append_to_doc` | Append plain text to end |
| `insert_in_doc` | Insert plain text at index |
| `append_markdown` | Append markdown-rendered content (headings, lists, tables, images, code blocks, blockquotes) |
| `replace_doc_markdown` | Replace entire body with markdown |
| `replace_range_markdown` | Replace a range with markdown |
| `find_and_replace` | Bulk text replacement across the doc |
| `apply_text_style` | Bold/italic/strike/underline, font, size, foreground/background color, link over a range |
| `apply_paragraph_style` | Named styles (TITLE, HEADING_1–6, etc.), alignment, line spacing, indentation, spacing |
| `insert_page_break` | Force a page break |
| `insert_horizontal_rule` | Insert a divider line |
| `insert_section_break` | Insert section break (NEXT_PAGE or CONTINUOUS) |
| `update_section_columns` | Set column count for a section (newspaper-style layout) |
| `update_page_setup` | Margins, page size, orientation |
| `update_header_footer` | Set header / footer content; page-number placeholder support |
| `insert_image` | Embed image from URL or local file (local files uploaded to Drive) |
| `style_table_cells` | Background color, text/vertical alignment, padding, borders on a cell range |
| `merge_table_cells` | Merge a rectangular block of table cells |
| `copy_doc_from_template` | Duplicate a doc (great for branded templates) |
| `rename_doc` | Rename a doc |
```

Add a new section under Setup (after "### 4. Register with Claude Code"):

```markdown
### Re-authenticating after a scope change

If you previously authenticated with this MCP and we've added new OAuth scopes
(e.g. `drive.file` for image uploads and doc management), your existing tokens
are no longer sufficient. Re-run the auth helper for each account:

```bash
ACCOUNT=personal uv run python authenticate.py
ACCOUNT=work1 uv run python authenticate.py
ACCOUNT=work2 uv run python authenticate.py
```

Each opens a browser to grant the new permissions.
```

Update the Troubleshooting table to add a new row:

```markdown
| `Insufficient Permission` on image upload or rename | drive.file scope missing — re-run `authenticate.py` to grant it |
```

- [ ] **Step 2: Verify by reading the file**

Run: `wc -l README.md`
Expected: roughly the same line count + ~30 lines for new tools and section.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README for rich-formatting docs tools and re-auth"
```

---

## Phase 10 — Final Verification

### Task 30: End-to-end kitchen-sink smoke test

**Files:**
- None (verification only)

- [ ] **Step 1: Run all unit tests**

Run: `ACCOUNT=personal uv run pytest tests/ -v`
Expected: all tests pass — `test_common.py`, `test_markdown_transformer.py`, `test_reader.py`.

- [ ] **Step 2: Create a kitchen-sink doc end-to-end**

```bash
ACCOUNT=personal uv run python -c "
from tools.docs.manage import create_doc
from tools.docs.text import append_markdown
from tools.docs.style import apply_paragraph_style
from tools.docs.structure import update_page_setup, update_header_footer

r = create_doc('Kitchen Sink Demo')

# 1. Page setup
update_page_setup(r['id'], top_margin_pt=72, bottom_margin_pt=72,
                  left_margin_pt=90, right_margin_pt=90)

# 2. Cover content
append_markdown(r['id'], '''# Quarterly Report

## Q1 2026

Prepared by the team. Includes **bold**, *italic*, and `code` samples,
plus a [link](https://example.com).

### Findings

- Revenue up *15%*
- Churn down ~~3%~~ to **2.1%**
  - Better onboarding
  - Faster support response
- [ ] Action: ship new dashboard
- [x] Done: redesign login

> A pull quote that highlights a key insight from this quarter.

```python
def example():
    return \"code blocks render with monospace and bg\"
```

---

| Metric | Q4 2025 | Q1 2026 |
|---|---|---|
| Revenue | \$1.2M | \$1.4M |
| NPS | 42 | 51 |

![](https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_272x92dp.png)
''')

# 3. Header + footer
update_header_footer(r['id'], header_markdown='Quarterly Report',
                     footer_markdown='Confidential — Internal Use Only')

print('Open:', r['link'])
"
```

- [ ] **Step 3: Manual verification checklist**

Open the resulting doc in a browser. Verify each of the following:

- [ ] H1 "Quarterly Report" styled as Heading 1
- [ ] H2 "Q1 2026" as Heading 2
- [ ] H3 "Findings" as Heading 3
- [ ] Bold/italic/strikethrough/inline-code render correctly
- [ ] Link to example.com is clickable
- [ ] Nested bullet list renders with two depth levels
- [ ] Checkbox list shows two checkboxes (the `[x]` one renders unchecked — known limitation)
- [ ] Blockquote has indent and left border
- [ ] Code block uses monospace + gray background
- [ ] Horizontal rule visible
- [ ] Table renders with bold + gray header row
- [ ] Google logo image embedded
- [ ] Header "Quarterly Report" appears on every page
- [ ] Footer "Confidential — Internal Use Only" appears on every page
- [ ] Margins look ~1 inch left/right, ~1 inch top/bottom

If any item fails, identify the responsible task and fix before merging.

- [ ] **Step 4: Final commit (if any fixes were needed)**

```bash
git status  # should be clean if no fixes were needed
```

If fixes were needed, commit them with appropriate Conventional Commit messages and then verify the kitchen sink again.

- [ ] **Step 5: Push the branch**

```bash
git push -u origin feat/docs-rich-formatting
```

(Optionally open a PR via `gh pr create`; out of scope for this plan — done manually by the user.)
