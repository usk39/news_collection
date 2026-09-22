"""Google News RSS を使ったニュース検索モジュール。

Google News RSS はAPIキー不要で利用でき、日本語ニュースの検索・
トップニュース取得の両方に使える。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from xml.etree import ElementTree as ET

from config import (
    GOOGLE_NEWS_SEARCH_URL,
    GOOGLE_NEWS_TOP_URL,
    GOOGLE_NEWS_TOPIC_URL,
    HTTP_TIMEOUT,
    NEWS_LOOKBACK_DAYS,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})


def _parse_rss(xml_text: str) -> list[dict]:
    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("RSSの解析に失敗しました: %s", exc)
        return articles

    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else ""
        if not title or not link:
            continue
        articles.append(
            {
                "title": title,
                "link": link,
                "source": source,
                "published_at": pub_date,
            }
        )
    return articles


def _fetch(url: str, params: dict | None = None) -> list[dict]:
    try:
        resp = _session.get(url, params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("ニュース取得に失敗しました (%s): %s", url, exc)
        return []
    return _parse_rss(resp.text)


def search_news(query: str, lookback_days: int = NEWS_LOOKBACK_DAYS, max_results: int = 10) -> list[dict]:
    """キーワードでGoogle News RSSを検索する。"""
    if not query:
        return []
    q = f"{query} when:{lookback_days}d"
    url = f"{GOOGLE_NEWS_SEARCH_URL}?q={quote(q)}&hl=ja&gl=JP&ceid=JP:ja"
    articles = _fetch(url)
    return articles[:max_results]


def get_top_stories(max_results: int = 30) -> list[dict]:
    """Google News の日本トップストーリーを取得する。"""
    url = f"{GOOGLE_NEWS_TOP_URL}?hl=ja&gl=JP&ceid=JP:ja"
    return _fetch(url)[:max_results]


def get_topic_headlines(topic: str, max_results: int = 20) -> list[dict]:
    """指定トピック (NATION/WORLD/BUSINESS/TECHNOLOGY/ENTERTAINMENT/SCIENCE 等) の見出しを取得する。"""
    url = GOOGLE_NEWS_TOPIC_URL.format(topic=topic)
    url = f"{url}?hl=ja&gl=JP&ceid=JP:ja"
    return _fetch(url)[:max_results]
