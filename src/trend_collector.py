"""チャンネル視聴者が関心を持ちそうな一般トレンドニュースを収集するモジュール。

方針:
1. Google News のトップストーリー + カテゴリ別ヘッドライン (社会/国際/経済/IT/エンタメ/科学) を取得
2. カテゴリごとの重み (config.TREND_TOPIC_WEIGHTS) と、
   両チャンネルの過去動画から作った「関心キーワードプロファイル」との一致度を
   使ってスコアリングする
3. 重複を除去し、スコア順に上位N件を返す
"""

from __future__ import annotations

from config import MAX_GENERAL_TRENDS, TREND_TOPIC_WEIGHTS
from src.news_search import get_top_stories, get_topic_headlines
from src.relevance import dedupe_articles, score_by_keywords


def collect_general_trends(
    keyword_profile: list[str] | None = None,
    max_results: int = MAX_GENERAL_TRENDS,
) -> list[dict]:
    keyword_profile = keyword_profile or []

    collected: list[dict] = []

    for article in get_top_stories(max_results=40):
        collected.append({**article, "category": "トップストーリー", "topic_weight": 1.15})

    for topic, weight in TREND_TOPIC_WEIGHTS.items():
        for article in get_topic_headlines(topic, max_results=15):
            collected.append({**article, "category": topic, "topic_weight": weight})

    collected = dedupe_articles(collected)

    scored = []
    for article in collected:
        keyword_score = score_by_keywords(article["title"], keyword_profile)
        # トピックの重み + キーワード一致度 (視聴者の既存の関心との重なり) を合成
        total_score = article["topic_weight"] * (1.0 + keyword_score * 2.0)
        scored.append({**article, "interest_score": round(total_score, 3)})

    scored.sort(key=lambda a: a["interest_score"], reverse=True)
    return scored[:max_results]
