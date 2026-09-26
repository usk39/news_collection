"""指定チャンネルの直近動画 (と視聴者の反応) を取得するモジュール。

- YOUTUBE_API_KEY があれば YouTube Data API v3 を使い、動画の再生数・高評価数・
  コメント数、および上位コメント本文まで取得する。
- APIキーがない場合は YouTube の公開RSSフィード (直近15本、再生数・評価数付き) に
  フォールバックする。チャンネルIDが config に無い場合はチャンネルページから解決する。
"""

from __future__ import annotations

import logging
import re
from xml.etree import ElementTree as ET

import requests

from config import (
    COMMENT_VIDEOS_PER_CHANNEL,
    HTTP_TIMEOUT,
    MAX_COMMENTS_PER_VIDEO,
    MAX_VIDEOS_PER_CHANNEL,
    USER_AGENT,
    YOUTUBE_API_BASE,
    YOUTUBE_API_KEY,
    YOUTUBE_FEED_URL,
)

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ja,en;q=0.8"})

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
_CHANNEL_ID_RE = re.compile(r'(?:"channelId"|"externalId"|channel_id=)[":]*(UC[\w-]{22})')


class YouTubeCollectorError(RuntimeError):
    pass


# ------------------------------------------------------------------
# YouTube Data API v3
# ------------------------------------------------------------------
def _get(path: str, params: dict) -> dict:
    params = {**params, "key": YOUTUBE_API_KEY}
    resp = _session.get(f"{YOUTUBE_API_BASE}/{path}", params=params, timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        raise YouTubeCollectorError(
            f"YouTube API error {resp.status_code} for {path}: {resp.text[:300]}"
        )
    return resp.json()


def _resolve_channel_api(handle: str) -> dict | None:
    """@handle からチャンネルID・名前・アップロード再生リストIDを解決する。"""
    data = _get("channels", {"part": "snippet,contentDetails", "forHandle": handle.lstrip("@")})
    items = data.get("items", [])
    if not items:
        logger.warning("チャンネルが見つかりませんでした: %s", handle)
        return None
    item = items[0]
    return {
        "channel_id": item["id"],
        "title": item["snippet"].get("title", ""),
        "uploads": item["contentDetails"]["relatedPlaylists"]["uploads"],
    }


def _fetch_video_stats(video_ids: list[str]) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for i in range(0, len(video_ids), 50):
        data = _get("videos", {"part": "statistics", "id": ",".join(video_ids[i : i + 50])})
        for item in data.get("items", []):
            s = item.get("statistics", {})
            stats[item["id"]] = {
                "view_count": int(s.get("viewCount", 0)),
                "like_count": int(s.get("likeCount", 0)),
                "comment_count": int(s.get("commentCount", 0)),
            }
    return stats


def get_top_comments(video_id: str, max_results: int = MAX_COMMENTS_PER_VIDEO) -> list[str]:
    """動画の人気順コメント本文を取得する (APIキー必須)。コメント無効の動画は空リスト。"""
    if not YOUTUBE_API_KEY:
        return []
    try:
        data = _get(
            "commentThreads",
            {
                "part": "snippet",
                "videoId": video_id,
                "order": "relevance",
                "textFormat": "plainText",
                "maxResults": min(100, max_results),
            },
        )
    except YouTubeCollectorError as exc:
        logger.info("コメント取得をスキップ (%s): %s", video_id, str(exc)[:120])
        return []
    return [
        item["snippet"]["topLevelComment"]["snippet"].get("textDisplay", "")
        for item in data.get("items", [])
    ]


def _get_recent_videos_api(handle: str, max_results: int) -> tuple[dict, list[dict]]:
    channel = _resolve_channel_api(handle)
    if not channel:
        return {}, []

    videos: list[dict] = []
    page_token = None
    while len(videos) < max_results:
        params = {
            "part": "snippet",
            "playlistId": channel["uploads"],
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
    videos = videos[:max_results]

    stats = _fetch_video_stats([v["video_id"] for v in videos])
    for v in videos:
        v.update(stats.get(v["video_id"], {}))

    # 再生数の多い動画ほど視聴者の関心が高いので、上位動画のコメントを取得する
    for v in sorted(videos, key=lambda x: x.get("view_count", 0), reverse=True)[
        :COMMENT_VIDEOS_PER_CHANNEL
    ]:
        v["top_comments"] = get_top_comments(v["video_id"])

    return {"channel_id": channel["channel_id"], "title": channel["title"]}, videos


# ------------------------------------------------------------------
# RSS フォールバック (APIキー不要)
# ------------------------------------------------------------------
def resolve_channel_id_from_page(handle: str) -> str | None:
    """チャンネルページのHTMLからチャンネルID (UC...) を抜き出す。"""
    url = f"https://www.youtube.com/{handle if handle.startswith('@') else '@' + handle}"
    try:
        resp = _session.get(url, timeout=HTTP_TIMEOUT, cookies={"CONSENT": "YES+1"})
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("チャンネルページの取得に失敗しました (%s): %s", url, exc)
        return None
    match = _CHANNEL_ID_RE.search(resp.text)
    return match.group(1) if match else None


def parse_channel_feed(xml_text: str) -> tuple[dict, list[dict]]:
    """YouTube チャンネルRSS (Atom) をパースする。"""
    root = ET.fromstring(xml_text)
    channel = {
        "channel_id": root.findtext("yt:channelId", default="", namespaces=_NS),
        "title": root.findtext("atom:title", default="", namespaces=_NS),
    }
    videos = []
    for entry in root.findall("atom:entry", _NS):
        video_id = entry.findtext("yt:videoId", default="", namespaces=_NS)
        if not video_id:
            continue
        group = entry.find("media:group", _NS)
        description = ""
        view_count = like_count = 0
        if group is not None:
            description = group.findtext("media:description", default="", namespaces=_NS)
            community = group.find("media:community", _NS)
            if community is not None:
                stats_el = community.find("media:statistics", _NS)
                rating_el = community.find("media:starRating", _NS)
                if stats_el is not None:
                    view_count = int(stats_el.get("views", 0) or 0)
                if rating_el is not None:
                    like_count = int(rating_el.get("count", 0) or 0)
        videos.append(
            {
                "video_id": video_id,
                "title": entry.findtext("atom:title", default="", namespaces=_NS),
                "description": description,
                "published_at": entry.findtext("atom:published", default="", namespaces=_NS),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "view_count": view_count,
                "like_count": like_count,
            }
        )
    return channel, videos


def _get_recent_videos_rss(channel_conf: dict, max_results: int) -> tuple[dict, list[dict]]:
    channel_id = channel_conf.get("channel_id") or resolve_channel_id_from_page(channel_conf["handle"])
    if not channel_id:
        logger.warning(
            "%s のチャンネルIDを解決できませんでした。config.CHANNELS に channel_id を設定するか、"
            "YOUTUBE_API_KEY を設定してください。",
            channel_conf["handle"],
        )
        return {}, []
    try:
        resp = _session.get(YOUTUBE_FEED_URL, params={"channel_id": channel_id}, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        channel, videos = parse_channel_feed(resp.text)
    except (requests.RequestException, ET.ParseError) as exc:
        logger.warning("チャンネルRSSの取得に失敗しました (%s): %s", channel_id, exc)
        return {}, []
    return channel, videos[:max_results]


# ------------------------------------------------------------------
# 公開関数
# ------------------------------------------------------------------
def get_recent_videos(channel_conf: dict, max_results: int = MAX_VIDEOS_PER_CHANNEL) -> tuple[dict, list[dict]]:
    """チャンネルの直近動画を新しい順に取得する。

    戻り値: (チャンネル情報 {channel_id, title}, 動画リスト)
    動画の各要素: {video_id, title, description, published_at, url,
                  view_count, like_count, [comment_count], [top_comments]}
    """
    if YOUTUBE_API_KEY:
        try:
            return _get_recent_videos_api(channel_conf["handle"], max_results)
        except (YouTubeCollectorError, requests.RequestException) as exc:
            logger.warning("YouTube API での取得に失敗したためRSSにフォールバックします: %s", exc)
    else:
        logger.info("YOUTUBE_API_KEY 未設定のため、RSSフィードで %s の動画を取得します。", channel_conf["handle"])
    return _get_recent_videos_rss(channel_conf, max_results)
