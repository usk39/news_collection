"""海外ニュースサイトからニュースを収集・スコアリングするモジュール。

データソース
- config.OVERSEAS_FEEDS: BBC / Guardian / Al Jazeera / Fox News / Deadline など海外各社のRSS
- 英語版 Google News (US/GB): 動画キーワードの英訳で検索 + トップストーリー

提供する機能
- collect_overseas_for_video: 動画のテーマ (英訳キーワード) に関連する海外記事
- collect_overseas_trends: 視聴者の関心プロファイルと「何社が報じているか」で
  スコアリングした、海外で話題のニュース
- collect_japan_in_overseas: 海外メディアが日本について報じている記事
"""

from __future__ import annotations

import html
import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests

from config import (
    GOOGLE_NEWS_SEARCH_URL,
    GOOGLE_NEWS_TOP_URL,
    HTTP_TIMEOUT,
    MAX_JAPAN_IN_OVERSEAS,
    MAX_OVERSEAS_NEWS_PER_VIDEO,
    MAX_OVERSEAS_TRENDS,
    NEWS_LOOKBACK_DAYS,
    OVERSEAS_CATEGORY_WEIGHTS,
    OVERSEAS_FEEDS,
    OVERSEAS_GOOGLE_NEWS_EDITIONS,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})

_TAG_RE = re.compile(r"<[^>]+>")
_WORD_RE = re.compile(r"[a-z0-9']+")
_JAPAN_RE = re.compile(
    r"\b(japan|japanese|tokyo|osaka|kyoto|okinawa|hokkaido|fukushima|yen|nikkei|"
    r"ishiba|takaichi|kishida|toyota|sony|nintendo|softbank)\b",
    re.IGNORECASE,
)
_EN_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are", "was", "were",
    "at", "by", "with", "from", "as", "after", "over", "into", "its", "it", "be", "has", "have",
    "says", "said", "new", "how", "why", "what", "who", "will", "not", "but", "this", "that",
    "his", "her", "their", "he", "she", "they", "up", "out", "about", "more", "than", "amid",
}


# ------------------------------------------------------------------
# RSS / Atom / RDF の汎用パーサ
# ------------------------------------------------------------------
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(el: ET.Element, *names: str) -> str:
    for child in el:
        if _local(child.tag) in names and child.text:
            return child.text.strip()
    return ""


def _child_link(el: ET.Element) -> str:
    for child in el:
        if _local(child.tag) != "link":
            continue
        if child.text and child.text.strip():
            return child.text.strip()
        href = child.get("href")
        if href and child.get("rel", "alternate") == "alternate":
            return href
    return ""


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", text or ""))).strip()


def parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_feed(xml_text: str, default_source: str = "") -> list[dict]:
    """RSS 2.0 / Atom / RSS 1.0(RDF) のどれでも記事リストに変換する。"""
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError as exc:
        logger.warning("フィードの解析に失敗しました (%s): %s", default_source, exc)
        return []

    articles = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        title = _strip_html(_child_text(el, "title"))
        link = _child_link(el)
        if not title or not link:
            continue
        source = default_source
        for child in el:
            # RSS 2.0 の <source> (名前空間なし) のみ媒体名として使う。
            # dc:source / media:credit などの写真クレジット等は無視する
            if child.tag == "source" and child.text:
                source = child.text.strip()
        published = _child_text(el, "pubDate", "published", "updated", "date")
        summary = _strip_html(_child_text(el, "description", "summary", "encoded"))[:400]
        # Google News の見出しは「タイトル - 媒体名」形式なので媒体名を落とす
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        dt = parse_date(published)
        articles.append(
            {
                "title": title,
                "link": link,
                "source": source,
                "summary": summary,
                "published_at": dt.isoformat() if dt else published,
            }
        )
    return articles


def _fetch_feed(url: str, source: str = "", params: dict | None = None) -> list[dict]:
    try:
        resp = _session.get(url, params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("海外フィード取得に失敗しました (%s): %s", source or url, exc)
        return []
    return parse_feed(resp.content.decode(resp.encoding or "utf-8", errors="replace"), source)


# ------------------------------------------------------------------
# 取得
# ------------------------------------------------------------------
def fetch_overseas_feeds(feeds: list[dict] = OVERSEAS_FEEDS) -> list[dict]:
    """海外各社のRSSを並列取得し、category を付与して返す。"""

    def _one(feed: dict) -> list[dict]:
        return [
            {**a, "category": feed["category"]}
            for a in _fetch_feed(feed["url"], feed["name"])
        ]

    pool: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for articles in ex.map(_one, feeds):
            pool.extend(articles)

    # 英語版 Google News のトップストーリーも候補に加える (複数媒体のまとめ見出し)
    for ed in OVERSEAS_GOOGLE_NEWS_EDITIONS[:1]:
        for a in _fetch_feed(GOOGLE_NEWS_TOP_URL, "Google News (EN)", params=ed):
            pool.append({**a, "category": "world"})

    return filter_recent(dedupe(pool))


def search_overseas_news(en_keywords: list[str], max_terms: int = 3, lookback_days: int = NEWS_LOOKBACK_DAYS) -> list[dict]:
    """英訳キーワードで英語版 Google News (US/GB) を検索する。"""
    terms = [k for k in en_keywords if k][:max_terms]
    if not terms:
        return []
    query = " OR ".join(f'"{t}"' for t in terms) + f" when:{lookback_days}d"
    results: list[dict] = []
    for ed in OVERSEAS_GOOGLE_NEWS_EDITIONS:
        for a in _fetch_feed(GOOGLE_NEWS_SEARCH_URL, "", params={"q": query, **ed}):
            results.append({**a, "category": "search"})
    return dedupe(results)


# ------------------------------------------------------------------
# スコアリングユーティリティ
# ------------------------------------------------------------------
def _tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if w not in _EN_STOPWORDS and len(w) > 1}


def keyword_in_text(keyword: str, text: str) -> bool:
    """英語キーワードが単語境界付きでテキストに含まれるか (大文字小文字は無視)。"""
    if not keyword:
        return False
    pattern = r"(?<![A-Za-z0-9])" + re.escape(keyword) + r"(?![A-Za-z0-9])"
    return re.search(pattern, text or "", re.IGNORECASE) is not None


def dedupe(articles: list[dict]) -> list[dict]:
    seen_links: set[str] = set()
    seen_titles: set[str] = set()
    result = []
    for a in articles:
        norm = re.sub(r"\W+", "", a.get("title", "").lower())
        if a.get("link") in seen_links or (norm and norm in seen_titles):
            continue
        seen_links.add(a.get("link"))
        seen_titles.add(norm)
        result.append(a)
    return result


def filter_recent(articles: list[dict], lookback_days: int = NEWS_LOOKBACK_DAYS, now: datetime | None = None) -> list[dict]:
    """日付が分かる記事のうち古いものを除外する (日付不明の記事は残す)。"""
    now = now or datetime.now(timezone.utc)
    limit = now - timedelta(days=lookback_days)
    kept = []
    for a in articles:
        dt = parse_date(a.get("published_at", ""))
        if dt is None or dt >= limit:
            kept.append(a)
    return kept


def recency_factor(published_at: str, now: datetime | None = None) -> float:
    """24時間以内=1.0、以降は緩やかに減衰して7日後に約0.6。日付不明は0.8。"""
    dt = parse_date(published_at)
    if dt is None:
        return 0.8
    now = now or datetime.now(timezone.utc)
    hours = max(0.0, (now - dt).total_seconds() / 3600)
    if hours <= 24:
        return 1.0
    return max(0.5, 1.0 - 0.4 * (hours - 24) / (24 * 6))


def score_keyword_match(article: dict, en_keywords: list[str]) -> float:
    """キーワード一致度 (0〜1)。タイトル一致を本文要約一致の2倍に評価する。"""
    if not en_keywords:
        return 0.0
    total = 0.0
    for kw in en_keywords:
        if keyword_in_text(kw, article.get("title", "")):
            total += 1.0
        elif keyword_in_text(kw, article.get("summary", "")):
            total += 0.5
    return total / len(en_keywords)


def score_profile_match(article: dict, profile: dict[str, float]) -> tuple[float, list[str]]:
    """重み付き関心プロファイルとの一致度と、一致したキーワードを返す。"""
    score = 0.0
    matched = []
    for kw, weight in profile.items():
        if keyword_in_text(kw, article.get("title", "")):
            score += weight
            matched.append(kw)
        elif keyword_in_text(kw, article.get("summary", "")):
            score += weight * 0.5
            matched.append(kw)
    return min(score, 2.0), matched


def annotate_coverage(articles: list[dict], threshold: float = 0.35) -> list[dict]:
    """似た見出しを報じている「別の媒体の数」を coverage として付与する。

    多くの海外メディアが同時に報じている = 国際的に大きなニュース、とみなす。
    """
    token_sets = [_tokens(a.get("title", "")) for a in articles]
    result = []
    for i, a in enumerate(articles):
        sources = {a.get("source", "")}
        ti = token_sets[i]
        if len(ti) >= 3:
            for j, tj in enumerate(token_sets):
                if i == j or len(tj) < 3:
                    continue
                jaccard = len(ti & tj) / len(ti | tj)
                if jaccard >= threshold:
                    sources.add(articles[j].get("source", ""))
        result.append({**a, "coverage": len(sources)})
    return result


def is_japan_related(article: dict) -> bool:
    return bool(_JAPAN_RE.search(article.get("title", "") + " " + article.get("summary", "")))


# ------------------------------------------------------------------
# 収集ロジック
# ------------------------------------------------------------------
def collect_overseas_for_video(
    en_keywords: list[str],
    feed_pool: list[dict],
    top_n: int = MAX_OVERSEAS_NEWS_PER_VIDEO,
    search: bool = True,
) -> list[dict]:
    """動画テーマの英訳キーワードに関連する海外記事を返す。"""
    if not en_keywords:
        return []
    candidates = [a for a in feed_pool if score_keyword_match(a, en_keywords) > 0]
    if search:
        candidates += search_overseas_news(en_keywords)
    candidates = filter_recent(dedupe(candidates))

    scored = []
    for a in candidates:
        rel = score_keyword_match(a, en_keywords)
        if rel <= 0:
            # Google News 検索結果はタイトルに語が無くても本文で一致していることがあるので低めに残す
            if a.get("category") != "search":
                continue
            rel = 0.1
        scored.append({**a, "relevance_score": round(rel * recency_factor(a.get("published_at", "")), 3)})
    scored.sort(key=lambda a: a["relevance_score"], reverse=True)
    return scored[:top_n]


def collect_overseas_trends(
    feed_pool: list[dict],
    profile: dict[str, float],
    top_n: int = MAX_OVERSEAS_TRENDS,
) -> list[dict]:
    """海外で話題 + 視聴者が関心を持ちそうなニュースをスコア順に返す。

    score = カテゴリ重み × (1 + 関心一致度) × (1 + 報道媒体数ボーナス) × 鮮度
    """
    scored = []
    for a in annotate_coverage(feed_pool):
        cat_w = OVERSEAS_CATEGORY_WEIGHTS.get(a.get("category", ""), 1.0)
        interest, matched = score_profile_match(a, profile)
        coverage_bonus = 0.3 * math.log2(a["coverage"]) if a["coverage"] > 1 else 0.0
        score = cat_w * (1.0 + interest) * (1.0 + coverage_bonus) * recency_factor(a.get("published_at", ""))
        scored.append(
            {**a, "interest_score": round(score, 3), "matched_keywords": matched}
        )
    scored.sort(key=lambda a: a["interest_score"], reverse=True)
    return _diversify(scored, top_n)


def collect_japan_in_overseas(feed_pool: list[dict], top_n: int = MAX_JAPAN_IN_OVERSEAS) -> list[dict]:
    """海外メディア (日本の媒体を除く) が日本について報じている記事。"""
    domestic = {"The Japan Times", "NHK WORLD"}
    candidates = [a for a in feed_pool if a.get("source") not in domestic and is_japan_related(a)]
    candidates += [
        a for a in search_overseas_news(["Japan", "Japanese"], max_terms=2)
        if is_japan_related(a)
    ]
    candidates = annotate_coverage(filter_recent(dedupe(candidates)))
    for a in candidates:
        a["interest_score"] = round(
            (1.0 + 0.3 * math.log2(max(1, a["coverage"]))) * recency_factor(a.get("published_at", "")), 3
        )
    candidates.sort(key=lambda a: a["interest_score"], reverse=True)
    return _diversify(candidates, top_n)


def _diversify(articles: list[dict], top_n: int, max_per_source: int = 4) -> list[dict]:
    """同じ媒体ばかりにならないよう、1媒体あたりの件数を制限する。"""
    per_source: dict[str, int] = {}
    result = []
    for a in articles:
        src = a.get("source", "")
        if per_source.get(src, 0) >= max_per_source:
            continue
        per_source[src] = per_source.get(src, 0) + 1
        result.append(a)
        if len(result) >= top_n:
            break
    return result
