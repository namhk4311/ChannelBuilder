"""
TikTok OAuth helper — generate authorize URL, exchange code for token, refresh token.

Đọc env qua root config.py (KHÔNG load_dotenv riêng).

Usage (chạy module, không import từ code khác):
  python -m agents.publisher.oauth url              → print authorize URL
  python -m agents.publisher.oauth token <code>     → exchange code → tokens.json
  python -m agents.publisher.oauth refresh          → refresh access token
"""

import json
import secrets
import sys
import urllib.parse
from pathlib import Path

import requests

from config import (
    TIKTOK_CLIENT_KEY,
    TIKTOK_CLIENT_SECRET,
    TIKTOK_REDIRECT_URI,
    TIKTOK_SCOPES,
)

TOKEN_FILE = Path(__file__).parent / "tokens.json"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


def _require_creds() -> tuple[str, str, str]:
    """Check 3 OAuth creds tại thời điểm gọi (KHÔNG ở module load) — tránh crash import."""
    missing = [
        name for name, val in (
            ("TIKTOK_CLIENT_KEY", TIKTOK_CLIENT_KEY),
            ("TIKTOK_CLIENT_SECRET", TIKTOK_CLIENT_SECRET),
            ("TIKTOK_REDIRECT_URI", TIKTOK_REDIRECT_URI),
        ) if not val
    ]
    if missing:
        raise SystemExit(f"Thiếu env vars trong .env: {', '.join(missing)}")
    return TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REDIRECT_URI


def build_authorize_url() -> str:
    client_key, _, redirect_uri = _require_creds()
    params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": TIKTOK_SCOPES,
        "redirect_uri": redirect_uri,
        "state": secrets.token_urlsafe(16),
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(code: str) -> dict:
    client_key, client_secret, redirect_uri = _require_creds()
    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    data = resp.json()
    if "access_token" not in data:
        raise SystemExit(f"Token exchange failed: {json.dumps(data, indent=2)}")
    TOKEN_FILE.write_text(json.dumps(data, indent=2))
    print(f"Saved tokens to {TOKEN_FILE}")
    print(f"  open_id:    {data.get('open_id')}")
    print(f"  scope:      {data.get('scope')}")
    print(f"  expires_in: {data.get('expires_in')}s (access token)")
    print(f"  refresh_expires_in: {data.get('refresh_expires_in')}s")
    return data


def refresh_token() -> dict:
    client_key, client_secret, _ = _require_creds()
    saved = json.loads(TOKEN_FILE.read_text())
    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": saved["refresh_token"],
        },
        timeout=30,
    )
    data = resp.json()
    if "access_token" not in data:
        raise SystemExit(f"Refresh failed: {json.dumps(data, indent=2)}")
    TOKEN_FILE.write_text(json.dumps(data, indent=2))
    print(f"Refreshed. New access token saved to {TOKEN_FILE}")
    return data


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "url":
        print(build_authorize_url())
    elif cmd == "token" and len(sys.argv) > 2:
        exchange_code(sys.argv[2])
    elif cmd == "refresh":
        refresh_token()
    else:
        print(__doc__)
