"""YouTube Data API v3 を使って、指定チャンネルの直近動画一覧を取得するモジュール。

YOUTUBE_API_KEY (環境変数) が必要。
API キー未設定の場合は例外を投げず空リストを返し、呼び出し側で
「動画紐づけニュース」をスキップできるようにする。
"""

from __future__ import annotations

import logging

import requests

from config import (
    HTTP_TIMEOUT,
    MAX_VIDEOS_PER_CHANNEL,
    USER_AGENT,
    YOUTUBE_API_BASE,
    YOUTUBE_API_KEY,
)

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})


class YouTubeCollectorError(RuntimeError):
    pass


def _get(path: str, params: dict) -> dict:
    params = {**params, "key": YOUTUBE_API_KEY}
    resp = _session.get(f"{YOUTUBE_API_BASE}/{path}", params=params, timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        raise YouTubeCollectorError(
            f"YouTube API error {resp.status_code} for {path}: {resp.text[:300]}"
        )
    return resp.json()


def resolve_channel_id(handle: str) -> str | None:
    """@handle からチャンネルIDを解決する。"""
    handle = handle.lstrip("@")
    data = _get(
        "channels",
        {"part": "id,snippet,contentDetails", "forHandle": handle},
    )
    items = data.get("items", [])
    if not items:
        logger.warning("チャンネルが見つかりませんでした: @%s", handle)
        return None
    return items[0]["id"]


def get_uploads_playlist_id(channel_id: str) -> str | None:
    data = _get(
        "channels",
        {"part": "contentDetails", "id": channel_id},
    )
    items = data.get("items", [])
    if not items:
        return None
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def get_recent_videos(handle: str, max_results: int = MAX_VIDEOS_PER_CHANNEL) -> list[dict]:
    """指定チャンネルの直近動画を新しい順に取得する。

    戻り値の各要素: {video_id, title, description, published_at, url}
    """
    if not YOUTUBE_API_KEY:
        logger.warning(
            "YOUTUBE_API_KEY が未設定のため、%s の動画取得をスキップします。", handle
        )
        return []

    channel_id = resolve_channel_id(handle)
    if not channel_id:
        return []

    uploads_playlist_id = get_uploads_playlist_id(channel_id)
    if not uploads_playlist_id:
        return []

    videos: list[dict] = []
    page_token = None
    while len(videos) < max_results:
        params = {
            "part": "snippet",
            "playlistId": uploads_playlist_id,
            "maxResults": min(50, max_results - len(videos)),
        }
        if page_token:
            params["pageToken"] = page_token

        data = _get("playlistItems", params)
        for item in data.get("items", []):
            snippet = item["snippet"]
            video_id = snippet.get("resourceId", {}).get("videoId")
            if not video_id:
                continue
            videos.append(
                {
                    "video_id": video_id,
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                }
            )

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return videos[:max_results]
