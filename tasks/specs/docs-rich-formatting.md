# Google Docs — Rich Formatting & Styling Tools

**Status:** Design complete · awaiting implementation plan
**Date:** 2026-05-11
**Owner:** Gabriel
**Branch:** `feat/docs-rich-formatting`

---

## 1. Motivation

The current Google Docs surface (`tools/docs.py`) exposes 5 tools: `search_docs`, `read_doc` (plain text), `create_doc`, `append_to_doc`, `insert_in_doc`. The LLM can only push plain text — no headings, no styles, no tables, no images, no headers/footers. Authoring a polished proposal, report, brief, or runbook requires manual cleanup in the browser.

This spec adds ~16 tools to let the LLM produce compelling, well-formatted Google Docs end-to-end. The authoring model is **hybrid**: markdown for body content + granular tools for the polish markdown can't express.

Reference for comparison: [a-bonus/google-docs-mcp](https://github.com/a-bonus/google-docs-mcp) (~25 TypeScript tools). This spec is broader in scope (headers/footers, columns, page setup, named styles, templates) and Python-native.

## 2. Dependencies Check

Must exist before starting:

- Python 3.10+ — present
- `mcp>=1.2.0`, `google-api-python-client`, `google-auth-oauthlib` — present in `pyproject.toml`
- `auth.py` with `get_service()` helper — present
- `app.py` exporting the shared `FastMCP` instance — present
- Three configured accounts under `accounts/` (`ibica`, `idcr`, `personal`) — present
- New dependency: `markdown-it-py>=3.0.0` — to be added

Pre-flight check before merging: all three account holders are available to re-authenticate (the new `drive.file` scope invalidates existing tokens).

## 3. Requirements

Numbered, code-level detail.

1. Add `https://www.googleapis.com/auth/drive.file` to `SCOPES` in `auth.py`.
2. Convert `tools/docs.py` (single file, 5 tools) into a `tools/docs/` package containing public tool modules and private helper modules (`_common.py`, `_markdown.py`, `_reader.py`).
3. The `tools/docs/__init__.py` MUST import every public submodule so that `@mcp.tool()` decorators register on package import. `server.py` requires no changes.
4. Existing 5 tools (`search_docs`, `read_doc`, `create_doc`, `append_to_doc`, `insert_in_doc`) MUST continue to work with their current signatures. `create_doc` and `read_doc` get optional parameters; defaults preserve current behavior.
5. Implement a markdown → Docs API request transformer in `_markdown.py` using `markdown-it-py` AST + a custom walker. All transforms produce a list of `Request` dicts suitable for `documents.batchUpdate`.
6. Implement a Docs JSON → markdown export in `_reader.py` to support `read_doc(format='markdown')`.
7. Implement all tools listed in §6 with the signatures spelled out there.
8. Every tool returns either a result dict or `{"error": "<message>"}`. No exceptions cross the MCP boundary.
9. Multi-step operations use a single `batchUpdate` call where possible. Documented exceptions: table cell population (2-step: insert table, then re-read indices, then populate) and local-image insertion (2-step: upload to Drive, then embed).
10. Add unit tests for `_markdown.py` in `tests/test_markdown_transformer.py` covering each markdown element class.
11. Update `README.md` Docs section to list new tools and document the one-time re-auth requirement.

## 4. Out of Scope (v1)

- Auto-inserted Table of Contents — Docs API has no native `insertTableOfContents` request. Documented as a known limitation.
- Comments thread (list/add/reply/resolve) — defer to v2.
- Multi-tab document support (`addTab`, `listTabs`, `renameTab`) — defer.
- Footnotes — defer.
- Equations, charts (Sheets handles charts), drawings — out of scope.
- Bookmarks / cross-references — defer.

## 5. File Structure

```
tools/
└── docs/
    ├── __init__.py        # re-imports all public submodules
    ├── _common.py         # _docs(), _drive(), color/length parsing, batch helpers
    ├── _markdown.py       # markdown → Docs API request transformer
    ├── _reader.py         # Docs JSON → markdown export
    ├── manage.py          # search_docs, create_doc, copy_doc_from_template, rename_doc
    ├── text.py            # read_doc, append_to_doc, insert_in_doc,
    │                      # append_markdown, replace_doc_markdown,
    │                      # replace_range_markdown, find_and_replace
    ├── style.py           # apply_text_style, apply_paragraph_style
    ├── structure.py       # insert_page_break, insert_horizontal_rule,
    │                      # insert_section_break, update_section_columns,
    │                      # update_page_setup, update_header_footer
    ├── media.py           # insert_image
    └── tables.py          # style_table_cells, merge_table_cells

tests/
└── test_markdown_transformer.py
```

Underscore-prefixed modules are private (no `@mcp.tool()` decorators).

## 6. Tool Signatures

Every signature spelled out. All tools return `dict`. Errors return `{"error": "<message>", ...}`.

### 6.1 Layer 1 — Bulk authoring (`manage.py`, `text.py`)

```python
# Unchanged
def search_docs(query: str, max_results: int = 20) -> list[dict]
def append_to_doc(document_id: str, text: str) -> dict
def insert_in_doc(document_id: str, text: str, index: int) -> dict

# Modified — backwards-compatible: new params optional, defaults preserve old behavior
def create_doc(title: str, markdown: Optional[str] = None,
               content: Optional[str] = None) -> dict
    # `markdown` (new) takes precedence over `content`. If both None, empty doc.
    # `content` (existing) preserved for backwards compat.

def read_doc(document_id: str,
             format: Literal["markdown", "text", "json"] = "markdown") -> dict
    # markdown: structured export (default — NEW default behavior)
    # text:     current plain-text behavior (10k char cap)
    # json:     full Docs structure incl. indices (no cap)
    # Note: default change is intentional — markdown is the more useful format
    # for LLM context. Callers wanting old behavior pass format="text".

# New
def append_markdown(document_id: str, markdown: str) -> dict
def replace_doc_markdown(document_id: str, markdown: str) -> dict
def replace_range_markdown(document_id: str, start_index: int,
                            end_index: int, markdown: str) -> dict
def find_and_replace(document_id: str, find: str, replace: str,
                     match_case: bool = False) -> dict
```

### 6.2 Layer 2 — Text & paragraph polish (`style.py`)

```python
def apply_text_style(
    document_id: str,
    start_index: int,
    end_index: int,
    bold: Optional[bool] = None,
    italic: Optional[bool] = None,
    underline: Optional[bool] = None,
    strikethrough: Optional[bool] = None,
    font_family: Optional[str] = None,           # e.g. "Roboto", "Roboto Mono"
    font_size_pt: Optional[float] = None,
    foreground_color: Optional[str] = None,      # "#ff8800" or "red"
    background_color: Optional[str] = None,
    link_url: Optional[str] = None,
) -> dict

def apply_paragraph_style(
    document_id: str,
    start_index: int,
    end_index: int,
    named_style: Optional[Literal[
        "TITLE", "SUBTITLE",
        "HEADING_1", "HEADING_2", "HEADING_3",
        "HEADING_4", "HEADING_5", "HEADING_6",
        "NORMAL_TEXT",
    ]] = None,
    alignment: Optional[Literal["START", "CENTER", "END", "JUSTIFIED"]] = None,
    line_spacing: Optional[float] = None,        # 1.0 = single, 1.15, 1.5, 2.0
    indent_first_line_pt: Optional[float] = None,
    indent_start_pt: Optional[float] = None,
    space_above_pt: Optional[float] = None,
    space_below_pt: Optional[float] = None,
    keep_with_next: Optional[bool] = None,
) -> dict
```

### 6.3 Layer 3 — Structure (`structure.py`)

```python
def insert_page_break(document_id: str, index: int) -> dict
def insert_horizontal_rule(document_id: str, index: int) -> dict
def insert_section_break(document_id: str, index: int,
                         type: Literal["NEXT_PAGE", "CONTINUOUS"] = "NEXT_PAGE") -> dict

def update_section_columns(document_id: str, section_start_index: int,
                            column_count: int, separator: bool = False) -> dict

def update_page_setup(
    document_id: str,
    top_margin_pt: Optional[float] = None,
    bottom_margin_pt: Optional[float] = None,
    left_margin_pt: Optional[float] = None,
    right_margin_pt: Optional[float] = None,
    page_width_pt: Optional[float] = None,
    page_height_pt: Optional[float] = None,
    orientation: Optional[Literal["portrait", "landscape"]] = None,
) -> dict

def update_header_footer(
    document_id: str,
    header_markdown: Optional[str] = None,
    footer_markdown: Optional[str] = None,
    include_page_numbers: bool = False,
    first_page_different: bool = False,
) -> dict
```

### 6.4 Layer 4 — Media + tables (`media.py`, `tables.py`)

```python
def insert_image(
    document_id: str,
    index: int,
    source: str,                          # URL OR local file path
    width_pt: Optional[float] = None,
    height_pt: Optional[float] = None,
) -> dict
    # If source starts with http(s)://, embed directly.
    # Else treat as local path: upload via Drive files.create, embed by Drive URL.

def style_table_cells(
    document_id: str,
    table_start_index: int,
    row_range: tuple[int, int],           # (start_row, end_row), inclusive 0-based
    col_range: tuple[int, int],
    background_color: Optional[str] = None,
    text_alignment: Optional[Literal["START", "CENTER", "END"]] = None,
    vertical_alignment: Optional[Literal["TOP", "MIDDLE", "BOTTOM"]] = None,
    padding_pt: Optional[float] = None,
    border_color: Optional[str] = None,
    border_width_pt: Optional[float] = None,
) -> dict

def merge_table_cells(
    document_id: str,
    table_start_index: int,
    row_start: int,
    col_start: int,
    row_end: int,
    col_end: int,
) -> dict
```

### 6.5 Layer 5 — Templates & doc management (`manage.py`)

```python
def copy_doc_from_template(template_id: str, new_title: str) -> dict
    # Calls drive.files.copy. Returns id, link, title.

def rename_doc(document_id: str, new_title: str) -> dict
    # Calls drive.files.update with name. Requires drive.file scope.
```

## 7. Markdown → Docs API Mapping

The transformer in `_markdown.py` walks the `markdown-it-py` AST. Two-pass per block:

1. **Pass 1** — emit all `insertText` requests, advancing a running cursor.
2. **Pass 2** — emit style requests targeting ranges produced in pass 1.

| Markdown source | Docs API requests |
|---|---|
| `# H1` … `###### H6` | `insertText` + `updateParagraphStyle(namedStyleType=HEADING_N)` |
| Paragraph | `insertText` + `updateParagraphStyle(namedStyleType=NORMAL_TEXT)` |
| `**bold**` | `insertText` + `updateTextStyle(bold=true)` over range |
| `*italic*` | `insertText` + `updateTextStyle(italic=true)` |
| `~~strike~~` | `updateTextStyle(strikethrough=true)` |
| `` `inline code` `` | `updateTextStyle(weightedFontFamily={fontFamily:"Roboto Mono"})` |
| `[text](url)` | `updateTextStyle(link={url:url})` |
| `- item` (unordered) | `insertText` + `createParagraphBullets(BULLET_DISC_CIRCLE_SQUARE)` |
| `1. item` (ordered) | `createParagraphBullets(NUMBERED_DECIMAL_ALPHA_ROMAN)` |
| `- [ ]` / `- [x]` | `createParagraphBullets(BULLET_CHECKBOX)`. API can't pre-check; `[x]` items render unchecked. Documented limitation. |
| `> blockquote` | `insertText` + `updateParagraphStyle(indentStart=18pt)` + left-border faked via `borderLeft` |
| ``` ```lang … ``` ``` (fenced) | `insertText` + `updateTextStyle(weightedFontFamily="Roboto Mono")` + `updateParagraphStyle(shading.backgroundColor=#f3f3f3, indentStart=10pt)` |
| `![alt](url-or-path)` | URL: `insertInlineImage(uri=url)`. Local path: `drive.files.create` → embed by returned URL. |
| GFM table | `insertTable(rows, columns)` → re-fetch doc → `insertText` into each cell by index. Header row gets bold + light gray bg. |
| `---` | `insertHorizontalRule` |
| Raw HTML blocks | Stripped with a warning logged to stderr |

**Bullet nesting.** Per Docs API convention, list nesting is conveyed by prefixing each item's text with `\t` characters (depth = number of tabs). The walker emits this and lets `createParagraphBullets` resolve the nest level.

**Tables — the 2-step pattern.**

```
1. insertTable(rows=R, columns=C) at index I
2. documents.get(documentId) to re-read structure
3. For each cell, locate its start index, emit insertText
4. Apply header-row styling: bold + #f3f3f3 bg over header range
```

Two round-trips per table. The reference repo uses the same approach.

## 8. Error Model

Three categories. All surfaced as dict.

| Category | Shape |
|---|---|
| Google API error | `{"error": "Docs API <status>: <reason>", "details": "<message>"}` |
| Validation error | `{"error": "Invalid <field>: <value>", "hint": "<expected format>"}` |
| Markdown parse error | `{"error": "Markdown parse failed", "location": "line N", "hint": "<message>"}` |

All public tools wrap their body in a `try/except HttpError`. Validation runs before any API call. Markdown errors are caught from `markdown-it-py` and rewrapped.

## 9. Edge Cases

Numbered. Each has explicit expected behavior.

1. **Empty markdown string** → return `{"status": "no-op", "id": "..."}`. No API call.
2. **Markdown with unsupported features** (raw HTML, custom directives) → strip with a stderr warning; don't fail.
3. **Image URL fetch fails server-side** (Docs API can't load image) → return `{"error": "Image load failed", "url": "..."}`. No partial doc state because the batch fails atomically.
4. **Local image path doesn't exist** → validation error before Drive call.
5. **Local image too large** (>10 MB Drive upload limit for simple upload) → validation error with hint.
6. **GFM table row count mismatch** (e.g., 4 cells in row 1, 3 in row 2) → markdown parse error with line number.
7. **Inserting at invalid index** (e.g., negative or past end) → API error surfaced.
8. **Color hex without leading `#`** → accepted (`f80` parsed as `#ff8800`).
9. **Unrecognized color name** → validation error listing acceptable inputs.
10. **Re-auth needed** (scope change) → `_get_credentials()` in `auth.py` already deletes invalid tokens and raises; user re-runs `authenticate.py`.
11. **Markdown larger than ~10 MB** → batch may exceed API limits; chunk into multiple batches in `_markdown.py` (>5000 requests per batch is the documented Docs API limit).
12. **`apply_text_style` on a range that crosses a table boundary** → Docs API will reject; surface the error.
13. **`update_header_footer` called twice** → second call replaces existing header/footer content.
14. **`copy_doc_from_template` on a doc not owned by the account** → Drive API permission error surfaced.
15. **`insert_image` with width but no height (or vice versa)** → preserve aspect ratio: fetch dimensions if URL, else require both for local files.

## 10. Auth & Scope Migration

`auth.py` SCOPES updated:

```python
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",   # NEW
]
```

All existing tokens (`accounts/*/token.json`) become invalid on first call. The existing refresh-fails path in `_get_credentials()` already deletes the bad token and surfaces a clear error. User runs `ACCOUNT=<name> uv run python authenticate.py` once per account.

`README.md` gets a migration callout under Troubleshooting.

## 11. Testing Strategy

**Unit tests** (`tests/test_markdown_transformer.py`, new file):

Pure-Python, no network. Each test feeds a markdown snippet to the transformer and asserts the resulting list of `Request` dicts matches expectation.

Coverage:
- Headings H1–H6 → correct named style
- Inline styles (bold, italic, strike, code, link) with overlapping ranges
- Unordered, ordered, checkbox lists with 3+ nesting levels
- GFM tables (with header detection)
- Fenced code blocks (font + bg shading)
- Blockquotes
- Images (URL and local path)
- Horizontal rules
- Mixed document (kitchen-sink fixture)
- Index accounting: cursor advances correctly after each block

No mocked Docs API integration tests — per project convention. Manual smoke test fills that role.

**Manual smoke test** (documented in spec only, not automated):

Create a "kitchen sink" doc that exercises every feature: H1–H6, bold/italic/strike/code/link, nested lists, checkboxes, tables with styled header, code block, image from URL, image from local path, page break, section break with 2 columns, custom margins, header with page numbers, custom font/color, named styles. Eyeball the result in Google Docs.

**Build verification**: `uv run python -c "import server"` confirms tool registration succeeds (no import errors).

## 12. Implementation Checkpoints

Each checkpoint is one commit. Commit messages use Conventional Commits.

1. **Scope + scaffold** (`feat(docs): expand drive.file scope and scaffold docs package`)
   - Files: `auth.py`, `pyproject.toml`, `tools/docs.py` → `tools/docs/__init__.py`, `tools/docs/_common.py`, `tools/docs/manage.py`, `tools/docs/text.py` (existing 5 tools migrated, signatures unchanged).
   - Verification: `uv run python -c "import server"` succeeds. Existing tools list unchanged via `claude mcp` inspection.
   - Re-auth all 3 accounts.

2. **Markdown transformer** (`feat(docs): add markdown to Docs API transformer`)
   - Files: `tools/docs/_markdown.py`, `tests/test_markdown_transformer.py`.
   - Verification: unit tests pass. No public tool changes yet.

3. **Reader + bulk markdown tools** (`feat(docs): add markdown read and bulk authoring tools`)
   - Files: `tools/docs/_reader.py`, `tools/docs/text.py` (extend with `append_markdown`, `replace_doc_markdown`, `replace_range_markdown`, `find_and_replace`; extend `read_doc` with format param; extend `create_doc` with markdown param).
   - Verification: smoke test creating a doc from a markdown fixture and reading it back; round-trip preserves headings and inline styles.

4. **Text & paragraph styling** (`feat(docs): add text and paragraph style tools`)
   - Files: `tools/docs/style.py`.
   - Verification: smoke test applying TITLE, HEADING_1, custom color, alignment to ranges of a test doc.

5. **Structure tools** (`feat(docs): add page setup, sections, headers and footers`)
   - Files: `tools/docs/structure.py`.
   - Verification: smoke test creating a doc with landscape orientation, custom margins, footer with page numbers.

6. **Media & tables** (`feat(docs): add image insertion and table styling`)
   - Files: `tools/docs/media.py`, `tools/docs/tables.py`.
   - Verification: smoke test inserting URL image, local image, table with styled header row, merged cells.

7. **Templates & rename** (`feat(docs): add template copy and rename tools`)
   - Files: `tools/docs/manage.py` (extend).
   - Verification: smoke test copying a template doc and renaming it.

8. **Docs + README** (`docs: update README with new docs tool surface and re-auth notes`)
   - Files: `README.md`.
   - Verification: README accurately lists every tool; re-auth procedure documented.

## 13. Open Questions

Flagged for resolution during or after implementation, not blocking the plan.

1. **Checkbox pre-checked state** — confirmed: API cannot pre-check. `[x]` markdown renders as unchecked checkbox. Acceptable per design review.
2. **Bullet nesting depth** — Docs API supports up to 9 levels per `createParagraphBullets` docs. Verify with kitchen-sink test.
3. **Header / footer markdown subset** — headers/footers have a restricted set of supported elements (no tables, no images per some API behavior). Test what works; document subset. Likely: text + page number placeholder + basic styling.
4. **Table cell text inheritance** — when inserting text into a cell that already has paragraph styling, does `apply_text_style` over a cell range affect borders? Verify in checkpoint 6.
5. **Drive image upload size** — simple upload caps at 5 MB; resumable upload supports larger. Start with simple; revisit if it becomes a constraint.

## 14. Risk Notes

- **Re-auth gates real use** of the new tools. If any of the 3 account holders isn't around to re-auth, that account's docs tools are broken until they do. Mitigation: ship the scope change in checkpoint 1 so re-auth happens early.
- **Index accounting bugs** in `_markdown.py` are the most likely source of silent corruption. Mitigation: heavy unit test coverage of the cursor logic, plus a "transformer dry-run" that returns the request list without sending it (useful for tests and debugging).
- **`markdown-it-py` AST shape** may differ subtly from expectations on edge inputs. Mitigation: pin a minor version in `pyproject.toml`.

---

## Hand-off

After this spec is approved, the next step is `writing-plans` to break checkpoints 1–8 into an executable plan with verification steps and rollback notes per step.
