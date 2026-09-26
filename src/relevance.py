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


def video_weights(videos: list[dict]) -> list[float]:
    """動画ごとの「視聴者の反応の強さ」の重みを返す。

    チャンネル内の再生数中央値に対する比率 (0.5〜3.0 にクリップ)。
    再生数が取れない場合は全て 1.0。よく再生された動画のテーマ = 視聴者の関心が強いテーマ。
    """
    views = sorted(v.get("view_count", 0) for v in videos if v.get("view_count"))
    if not views:
        return [1.0 for _ in videos]
    median = views[len(views) // 2] or 1
    return [
        min(3.0, max(0.5, v.get("view_count", 0) / median)) if v.get("view_count") else 1.0
        for v in videos
    ]


def build_weighted_profile(
    weighted_keywords: list[tuple[list[str], float]],
    top_n: int = 30,
) -> dict[str, float]:
    """(キーワードリスト, 重み) の組から、重み付き関心プロファイル {語: 0〜1} を作る。"""
    counter: Counter[str] = Counter()
    for keywords, weight in weighted_keywords:
        for kw in keywords:
            counter[kw] += weight
    top = counter.most_common(top_n)
    if not top:
        return {}
    max_w = top[0][1]
    return {word: round(w / max_w, 3) for word, w in top}
