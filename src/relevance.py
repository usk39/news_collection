"""ニュース記事の関連度スコアリング・重複排除ユーティリティ。"""

from __future__ import annotations

import re
from collections import Counter


def _normalize(text: str) -> str:
    text = re.sub(r"\s+", "", text or "")
    text = re.sub(r"[|｜\-－].*$", "", text)  # 「記事タイトル - 出典名」の出典部分を除去
    return text.lower()


def dedupe_articles(articles: list[dict]) -> list[dict]:
    """URLとタイトルの正規化文字列で重複記事を除去する。"""
    seen_links = set()
    seen_titles = set()
    result = []
    for article in articles:
        link = article.get("link", "")
        norm_title = _normalize(article.get("title", ""))
        if link in seen_links or (norm_title and norm_title in seen_titles):
            continue
        seen_links.add(link)
        if norm_title:
            seen_titles.add(norm_title)
        result.append(article)
    return result


def score_by_keywords(article_title: str, keywords: list[str]) -> float:
    """記事タイトルにキーワードがいくつ含まれるかでスコアリングする (0.0〜1.0)。"""
    if not keywords:
        return 0.0
    title = article_title
    hits = sum(1 for kw in keywords if kw and kw in title)
    return hits / len(keywords)


def rank_articles_by_keywords(articles: list[dict], keywords: list[str], top_n: int) -> list[dict]:
    scored = []
    for article in articles:
        score = score_by_keywords(article.get("title", ""), keywords)
        scored.append({**article, "relevance_score": round(score, 3)})
    scored.sort(key=lambda a: a["relevance_score"], reverse=True)
    return scored[:top_n]


def build_keyword_profile(all_video_keywords: list[list[str]], top_n: int = 30) -> list[str]:
    """複数動画のキーワードから、チャンネル全体の関心プロファイル(頻出語)を作る。"""
    counter: Counter[str] = Counter()
    for keywords in all_video_keywords:
        for kw in keywords:
            counter[kw] += 1
    return [word for word, _ in counter.most_common(top_n)]
