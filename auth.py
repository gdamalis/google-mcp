"""
Shared OAuth2 authentication module for Google APIs.

Reads the ACCOUNT environment variable to resolve per-account
credentials and token files from the accounts/ directory.
"""

import logging
import os
import sys
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
]

_HERE = Path(__file__).parent

ACCOUNT = os.environ.get("ACCOUNT")
if not ACCOUNT:
    print(
        "ERROR: ACCOUNT environment variable is required. "
        "Set it to one of: personal, work1, work2",
        file=sys.stderr,
    )
    sys.exit(1)

ACCOUNT_DIR = _HERE / "accounts" / ACCOUNT
CREDENTIALS_FILE = ACCOUNT_DIR / "credentials.json"
TOKEN_FILE = ACCOUNT_DIR / "token.json"

# Cache built services by (api_name, api_version)
_services: dict[tuple[str, str], object] = {}
_creds: Credentials | None = None


def _get_credentials() -> Credentials:
    """Load or refresh OAuth2 credentials."""
    global _creds

    if _creds and _creds.valid:
        return _creds

    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            f"credentials.json not found at {CREDENTIALS_FILE}. "
            "Download it from Google Cloud Console > APIs & Services > Credentials "
            f"and place it in {ACCOUNT_DIR}/"
        )

    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        logger.debug("Loaded cached token for account '%s'", ACCOUNT)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing expired token for account '%s'", ACCOUNT)
                creds.refresh(Request())
            except RefreshError:
                TOKEN_FILE.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Token refresh failed for account '{ACCOUNT}'. "
                    f"Deleted {TOKEN_FILE}. Restart the server to re-authenticate."
                )
        else:
            logger.info("Starting OAuth2 browser flow for account '%s'", ACCOUNT)
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json())
        logger.info("Saved token for account '%s' to %s", ACCOUNT, TOKEN_FILE)

    _creds = creds
    return creds


def get_service(api_name: str, api_version: str):
    """
    Build and return a cached Google API service.

    Examples:
        get_service("gmail", "v1")
        get_service("calendar", "v3")
        get_service("docs", "v1")
        get_service("sheets", "v4")
        get_service("drive", "v3")
    """
    key = (api_name, api_version)
    if key not in _services:
        creds = _get_credentials()
        _services[key] = build(api_name, api_version, credentials=creds)
        logger.debug("Built %s %s service for account '%s'", api_name, api_version, ACCOUNT)
    return _services[key]
