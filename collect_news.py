#!/usr/bin/env python3
"""すみおじじ (@sumiaojiji) / ぷくじじ (@pukujiji) の関連ニュース自動収集ツール。

やること:
1. 両チャンネルの直近動画を取得
2. 各動画のタイトル・概要欄からキーワードを抽出し、関連ニュースをGoogle News RSSで検索
3. 両チャンネルの動画テーマから「視聴者の関心プロファイル」を作成
4. そのプロファイルを使って、視聴者が関心を持ちそうな一般トレンドニュースをスコアリング・収集
5. Markdown / JSON レポートとして出力

使い方:
    export YOUTUBE_API_KEY=xxxxx   # 未設定でも一般トレンド収集のみ動作する
    python collect_news.py
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

from config import CHANNELS, MAX_NEWS_PER_VIDEO, MAX_VIDEOS_PER_CHANNEL, OUTPUT_DIR
from src.keyword_extractor import build_query, extract_keywords
from src.news_search import search_news
from src.relevance import build_keyword_profile, dedupe_articles, rank_articles_by_keywords
from src.report import write_report
from src.trend_collector import collect_general_trends
from src.youtube_collector import get_recent_videos

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("collect_news")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-videos", type=int, default=MAX_VIDEOS_PER_CHANNEL, help="チャンネルごとに取得する動画数"
    )
    parser.add_argument(
        "--output-dir", type=str, default=OUTPUT_DIR, help="レポート出力先ディレクトリ"
    )
    return parser.parse_args()


def collect_for_channel(channel: dict, max_videos: int) -> tuple[dict, list[list[str]]]:
    logger.info("チャンネル処理開始: %s (%s)", channel["name"], channel["handle"])
    videos = get_recent_videos(channel["handle"], max_results=max_videos)
    logger.info("  動画取得数: %d", len(videos))

    video_results = []
    all_keywords: list[list[str]] = []

    for video in videos:
        keywords = extract_keywords(video["title"], video["description"])
        all_keywords.append(keywords)

        query = build_query(keywords)
        raw_articles = search_news(query) if query else []
        raw_articles = dedupe_articles(raw_articles)
        related_news = rank_articles_by_keywords(raw_articles, keywords, MAX_NEWS_PER_VIDEO)

        video_results.append(
            {
                "video_id": video["video_id"],
                "title": video["title"],
                "url": video["url"],
                "published_at": video["published_at"],
                "keywords": keywords,
                "related_news": related_news,
            }
        )
        logger.info(
            "  動画「%s」: キーワード=%s / 関連ニュース=%d件",
            video["title"][:30],
            keywords,
            len(related_news),
        )

    return (
        {
            "name": channel["name"],
            "handle": channel["handle"],
            "videos": video_results,
        },
        all_keywords,
    )


def main() -> None:
    args = parse_args()

    by_channel = []
    all_keywords_flat: list[list[str]] = []

    for channel in CHANNELS:
        channel_result, keywords_lists = collect_for_channel(channel, args.max_videos)
        by_channel.append(channel_result)
        all_keywords_flat.extend(keywords_lists)

    keyword_profile = build_keyword_profile(all_keywords_flat)
    logger.info("関心キーワードプロファイル: %s", keyword_profile)

    logger.info("一般トレンドニュース収集中...")
    general_trends = collect_general_trends(keyword_profile)
    logger.info("  一般トレンドニュース取得数: %d", len(general_trends))

    result = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "channels": CHANNELS,
        "by_channel": by_channel,
        "keyword_profile": keyword_profile,
        "general_trends": general_trends,
    }

    json_path, md_path = write_report(result, args.output_dir)
    logger.info("レポート出力完了:")
    logger.info("  %s", json_path)
    logger.info("  %s", md_path)


if __name__ == "__main__":
    main()
