"""
First-time authentication helper.

Usage:
    ACCOUNT=personal uv run python authenticate.py
    ACCOUNT=work1 uv run python authenticate.py

Opens a browser for OAuth consent and saves the token.
Run this once per account before using the MCP server.
"""

from auth import _get_credentials, ACCOUNT

print(f"Authenticating account: {ACCOUNT}")
print("A browser window will open for Google sign-in...\n")

creds = _get_credentials()

if creds and creds.valid:
    print(f"\nAuthentication successful for account '{ACCOUNT}'!")
    print("You can now use the MCP server with Claude Code.")
else:
    print("\nAuthentication failed. Check the error messages above.")
