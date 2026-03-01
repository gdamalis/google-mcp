# Google MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server for Claude Code that provides 33 tools across Gmail, Google Calendar, Google Docs, Google Sheets, and Google Drive. Supports multiple Google accounts via environment variable isolation.

## Architecture

```
google/
├── app.py              # FastMCP instance (shared across modules)
├── auth.py             # OAuth2 flow, token caching, service builder
├── server.py           # Entry point — imports tool modules
├── authenticate.py     # First-time auth helper script
├── tools/
│   ├── gmail.py        # 13 tools — search, drafts, labels, trash
│   ├── calendar.py     #  6 tools — events CRUD, calendar listing
│   ├── docs.py         #  5 tools — search, read, create, edit
│   ├── sheets.py       #  6 tools — search, read, write, create
│   └── drive.py        #  3 tools — folder browsing, file search
└── accounts/
    ├── personal/       # credentials.json + token.json per account
    ├── work1/
    └── work2/
```

Each account runs as a separate MCP server process, differentiated by the `ACCOUNT` environment variable. No state is shared between accounts at runtime.

## Setup

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- A Google Cloud project with OAuth 2.0 credentials

### 1. Get Google Cloud credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or select an existing one)
3. **Enable APIs** — go to _APIs & Services > Library_ and enable:
   - Gmail API
   - Google Calendar API
   - Google Docs API
   - Google Sheets API
   - Google Drive API
4. **Configure OAuth consent screen** — go to _APIs & Services > OAuth consent screen_:
   - Choose "External" (or "Internal" for Workspace)
   - Fill in app name and support email
   - Add scopes: `gmail.modify`, `calendar`, `documents`, `spreadsheets`, `drive.readonly`
   - Under **Test users**, add the Google account email you want to authorize
5. **Create credentials** — go to _APIs & Services > Credentials_:
   - Click _Create Credentials > OAuth client ID_
   - Application type: **Desktop app**
   - Download the JSON file

### 2. Place credentials

Save the downloaded JSON as `credentials.json` in the account directory:

```bash
cp ~/Downloads/client_secret_*.json accounts/personal/credentials.json
```

Repeat for each account you want to set up.

### 3. Authenticate

Run the auth helper once per account to complete the OAuth browser flow:

```bash
ACCOUNT=personal uv run python authenticate.py
# Browser opens → sign in with your Google account → grant access
# token.json is saved automatically
```

### 4. Register with Claude Code

```bash
claude mcp add --transport stdio --scope user google-personal \
  --env ACCOUNT=personal \
  -- uv run --directory /path/to/google python server.py
```

Verify: `claude mcp list` should show the server as connected.

## Tools

### Gmail

| Tool | Description |
|---|---|
| `search_emails` | Search with Gmail query syntax (from:, subject:, label:, etc.) |
| `get_email` | Read full email content by message ID |
| `list_labels` | List all labels with message/thread counts |
| `create_draft` | Create a draft email (supports reply threading) |
| `update_draft` | Update an existing draft |
| `list_drafts` | List all drafts with summaries |
| `delete_draft` | Delete a draft |
| `create_label` | Create a custom label with optional color |
| `update_label` | Rename or recolor a label |
| `delete_label` | Delete a custom label |
| `modify_email_labels` | Batch add/remove labels on messages |
| `trash_messages` | Batch move messages to trash |
| `trash_by_search` | Search + trash with dry_run safety (default: preview only) |

### Calendar

| Tool | Description |
|---|---|
| `list_events` | List events within a time window |
| `get_event` | Get full event details |
| `create_event` | Create an event with attendees, location, timezone |
| `update_event` | Update event fields |
| `delete_event` | Delete an event |
| `list_calendars` | List all accessible calendars |

### Docs

| Tool | Description |
|---|---|
| `search_docs` | Search Drive for Google Docs |
| `read_doc` | Read document content as plain text |
| `create_doc` | Create a new document with optional content |
| `append_to_doc` | Append text to end of document |
| `insert_in_doc` | Insert text at a specific index |

### Sheets

| Tool | Description |
|---|---|
| `search_sheets` | Search Drive for spreadsheets |
| `read_sheet` | Read cell values (A1 notation) |
| `write_sheet` | Write values to cells |
| `append_to_sheet` | Append rows after existing data |
| `create_spreadsheet` | Create a new spreadsheet |
| `list_sheet_names` | List all sheets/tabs in a spreadsheet |

### Drive

| Tool | Description |
|---|---|
| `list_folder` | List files and subfolders in a Drive folder (including shared drives) |
| `search_drive` | Search all file types by name/content with optional type filter |
| `find_folder` | Find a folder by name to get its ID for browsing |

## Adding a New Account

```bash
# 1. Create the account directory
mkdir accounts/myaccount

# 2. Place credentials (from Google Cloud Console)
cp ~/Downloads/client_secret_*.json accounts/myaccount/credentials.json

# 3. Authenticate
ACCOUNT=myaccount uv run python authenticate.py

# 4. Register with Claude Code
claude mcp add --transport stdio --scope user google-myaccount \
  --env ACCOUNT=myaccount \
  -- uv run --directory /path/to/google python server.py
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `credentials.json not found` | Download OAuth client JSON from Google Cloud Console and place it in `accounts/{name}/` |
| `Token refresh failed` | Delete `accounts/{name}/token.json` and re-run `authenticate.py` |
| `403 Insufficient Permission` | Scopes changed — delete `token.json` and re-run `authenticate.py` |
| `ACCOUNT env var not set` | The server requires `ACCOUNT=name` to know which credentials to use |
| `json_invalid` error in terminal | Don't run `server.py` directly — use `authenticate.py` for auth, Claude Code launches the server |

## Security

- `credentials.json` and `token.json` are gitignored — never commit them
- Each account process is fully isolated; no cross-account data access is possible
- Gmail uses `gmail.modify` scope (no permanent delete capability)
- `trash_by_search` defaults to `dry_run=True` to prevent accidental mass deletion
