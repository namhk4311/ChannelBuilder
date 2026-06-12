"""
TikTokClient — core library for the Publisher agent.

Handles: token auto-refresh, video direct post (chunked upload), publish
status polling, and video metrics (requires video.list scope).

Setup:
  pip install requests python-dotenv
  .env next to this file:
    TIKTOK_CLIENT_KEY=...
    TIKTOK_CLIENT_SECRET=...
  tiktok_tokens.json must exist (created once via tiktok_oauth.py).

Usage:
    from tiktok_client import TikTokClient

    client = TikTokClient()
    result = client.post_video("video.mp4", "My caption #ai")
    # -> {"publish_id": "...", "video_id": "...", "status": "published"}

    metrics = client.get_video_metrics([result["video_id"]])
    # -> [{"id": "...", "view_count": 0, "like_count": 0, ...}]
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Optional

import requests

from config import TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET

BASE_DIR = Path(__file__).parent

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
VIDEO_QUERY_URL = "https://open.tiktokapis.com/v2/video/query/"

MAX_SINGLE_CHUNK = 64 * 1024 * 1024  # 64MB
CHUNK_SIZE = 10 * 1024 * 1024        # 10MB

METRIC_FIELDS = "id,title,create_time,view_count,like_count,comment_count,share_count"


class TikTokError(Exception):
    """Raised when a TikTok API call fails."""


class TikTokClient:
    def __init__(self, token_file: Optional[Path] = None):
        if not TIKTOK_CLIENT_KEY or not TIKTOK_CLIENT_SECRET:
            raise TikTokError(
                "TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET chưa set trong .env"
            )
        self.client_key = TIKTOK_CLIENT_KEY
        self.client_secret = TIKTOK_CLIENT_SECRET
        self.token_file = Path(token_file) if token_file else BASE_DIR / "tokens.json"
        if not self.token_file.exists():
            raise TikTokError(
                f"{self.token_file} not found. Run the OAuth flow first "
                "(python -m agents.publisher.oauth url)."
            )
        self._tokens = json.loads(self.token_file.read_text())
        # Track expiry locally; refresh 5 minutes before it lapses.
        self._expires_at = self._tokens.get("_expires_at", 0)

    # ---------- token management ----------

    @property
    def access_token(self) -> str:
        if time.time() > self._expires_at - 300:
            self._refresh()
        return self._tokens["access_token"]

    def _refresh(self) -> None:
        resp = requests.post(
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self._tokens["refresh_token"],
            },
            timeout=30,
        )
        data = resp.json()
        if "access_token" not in data:
            raise TikTokError(f"Token refresh failed: {json.dumps(data)}")
        data["_expires_at"] = time.time() + data.get("expires_in", 86400)
        self._tokens = data
        self._expires_at = data["_expires_at"]
        self.token_file.write_text(json.dumps(data, indent=2))

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    # ---------- publishing ----------

    def post_video(
        self,
        video_path: str | Path,
        caption: str,
        privacy_level: str = "SELF_ONLY",  # unaudited clients must use SELF_ONLY
        poll_timeout_s: int = 300,
    ) -> dict:
        """Upload and publish a local video file. Blocks until TikTok finishes
        processing. Returns {"publish_id", "video_id", "status"}."""
        video_path = Path(video_path)
        if not video_path.exists():
            raise TikTokError(f"Video file not found: {video_path}")
        video_size = video_path.stat().st_size

        # 1. init
        if video_size <= MAX_SINGLE_CHUNK:
            chunk_size, total_chunks = video_size, 1
        else:
            chunk_size = CHUNK_SIZE
            total_chunks = math.floor(video_size / chunk_size)

        resp = requests.post(
            INIT_URL,
            headers=self._headers(),
            json={
                "post_info": {
                    "title": caption,
                    "privacy_level": privacy_level,
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_size,
                    "chunk_size": chunk_size,
                    "total_chunk_count": total_chunks,
                },
            },
            timeout=30,
        )
        data = resp.json()
        if data.get("error", {}).get("code") not in (None, "ok"):
            raise TikTokError(f"Init failed: {json.dumps(data)}")
        publish_id = data["data"]["publish_id"]
        upload_url = data["data"]["upload_url"]

        # 2. upload chunks
        with open(video_path, "rb") as f:
            for i in range(total_chunks):
                start = i * chunk_size
                end = video_size - 1 if i == total_chunks - 1 else start + chunk_size - 1
                f.seek(start)
                chunk = f.read(end - start + 1)
                up = requests.put(
                    upload_url,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start}-{end}/{video_size}",
                    },
                    data=chunk,
                    timeout=300,
                )
                if up.status_code not in (200, 201, 206):
                    raise TikTokError(
                        f"Chunk {i + 1}/{total_chunks} upload failed "
                        f"({up.status_code}): {up.text}"
                    )

        # 3. poll status
        video_id = None
        deadline = time.time() + poll_timeout_s
        while time.time() < deadline:
            st = requests.post(
                STATUS_URL,
                headers=self._headers(),
                json={"publish_id": publish_id},
                timeout=30,
            ).json()
            status = st.get("data", {}).get("status")
            if status == "PUBLISH_COMPLETE":
                video_id = st["data"].get("publicaly_available_post_id") or None
                if isinstance(video_id, list):
                    video_id = video_id[0] if video_id else None
                return {
                    "publish_id": publish_id,
                    "video_id": str(video_id) if video_id else None,
                    "status": "published",
                }
            if status == "FAILED":
                raise TikTokError(f"Publish failed: {json.dumps(st)}")
            time.sleep(5)
        raise TikTokError(f"Timed out waiting for publish {publish_id}")

    # ---------- metrics ----------

    def get_video_metrics(self, video_ids: list[str]) -> list[dict]:
        """Fetch metrics for the authorized user's own videos.
        Requires the video.list scope. Max 20 ids per call."""
        if not video_ids:
            return []
        resp = requests.post(
            f"{VIDEO_QUERY_URL}?fields={METRIC_FIELDS}",
            headers=self._headers(),
            json={"filters": {"video_ids": [str(v) for v in video_ids[:20]]}},
            timeout=30,
        )
        data = resp.json()
        if data.get("error", {}).get("code") not in (None, "ok"):
            raise TikTokError(f"Metrics query failed: {json.dumps(data)}")
        return data.get("data", {}).get("videos", [])