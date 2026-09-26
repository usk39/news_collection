#!/usr/bin/env python3
"""@sumiaojiji / @pukujiji の関連ニュース自動収集ツール (国内 + 海外ニュースサイト)。

やること:
1. 両チャンネルの直近動画 (と再生数・人気コメント) を取得
2. 各動画のタイトル・概要欄からキーワードを抽出し、
   - 国内ニュース (日本語版 Google News)
   - 海外ニュース (キーワードを英訳 → 海外各社RSS + 英語版 Google News)
   から関連ニュースを収集
3. 再生数で重み付けした動画テーマ + 視聴者コメントから「視聴者の関心プロファイル」を作成
4. そのプロファイルを使って、視聴者が関心を持ちそうなニュースを国内・海外それぞれ収集
   さらに「海外メディアが報じる日本」も収集
5. Markdown / JSON レポートとして出力

使い方:
    export YOUTUBE_API_KEY=xxxxx   # 任意。未設定でもRSSで動画取得できる (コメント分析は不可)
    python collect_news.py
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

from config import (
    CHANNELS,
    INTEREST_SEED_KEYWORDS_EN,
    MAX_NEWS_PER_VIDEO,
    MAX_VIDEOS_PER_CHANNEL,
    OUTPUT_DIR,
)
from src import translator
from src.keyword_extractor import build_query, extract_keywords
from src.news_search import search_news
from src.overseas_news import (
    collect_japan_in_overseas,
    collect_overseas_for_video,
    collect_overseas_trends,
    fetch_overseas_feeds,
)
from src.relevance import (
    build_weighted_profile,
    dedupe_articles,
    rank_articles_by_keywords,
    video_weights,
)
from src.report import write_report
from src.trend_collector import collect_general_trends
from src.youtube_collector import get_recent_videos

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("collect_news")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--max-videos", type=int, default=MAX_VIDEOS_PER_CHANNEL, help="チャンネルごとに取得する動画数"
    )
    parser.add_argument("--output-dir", type=str, default=OUTPUT_DIR, help="レポート出力先ディレクトリ")
    parser.add_argument("--no-domestic", action="store_true", help="国内ニュース (日本語Google News) の収集を省略")
    parser.add_argument("--no-overseas", action="store_true", help="海外ニュースの収集を省略")
    return parser.parse_args()


def collect_for_channel(
    channel: dict, max_videos: int, feed_pool: list[dict], args: argparse.Namespace
) -> tuple[dict, list[tuple[list[str], float]]]:
    logger.info("チャンネル処理開始: %s", channel["handle"])
    channel_info, videos = get_recent_videos(channel, max_results=max_videos)
    name = channel_info.get("title") or channel["name"]
    logger.info("  %s: 動画取得数 %d", name, len(videos))

    weights = video_weights(videos)
    weighted_keywords: list[tuple[list[str], float]] = []
    video_results = []

    for video, weight in zip(videos, weights):
        keywords = extract_keywords(video["title"], video["description"])
        weighted_keywords.append((keywords, weight))

        # 人気コメントに出てくる語 = 視聴者が実際に反応しているポイント
        comment_keywords: list[str] = []
        if video.get("top_comments"):
            comment_keywords = extract_keywords("", "\n".join(video["top_comments"]), max_keywords=10)
            weighted_keywords.append((comment_keywords, 0.5 * weight))

        related_news = []
        if not args.no_domestic:
            query = build_query(keywords)
            raw = dedupe_articles(search_news(query)) if query else []
            related_news = rank_articles_by_keywords(raw, keywords, MAX_NEWS_PER_VIDEO)

        en_keywords: list[str] = []
        overseas_news = []
        if not args.no_overseas:
            en_keywords = translator.translate_keywords(keywords)
            overseas_news = collect_overseas_for_video(en_keywords, feed_pool)

        video_results.append(
            {
                "video_id": video["video_id"],
                "title": video["title"],
                "url": video["url"],
                "published_at": video["published_at"],
                "view_count": video.get("view_count"),
                "like_count": video.get("like_count"),
                "comment_count": video.get("comment_count"),
                "interest_weight": round(weight, 2),
                "keywords": keywords,
                "keywords_en": en_keywords,
                "comment_keywords": comment_keywords,
                "related_news": related_news,
                "overseas_news": overseas_news,
            }
        )
        logger.info(
            "  「%s」: KW=%s / EN=%s / 国内%d件 / 海外%d件",
            video["title"][:25],
            keywords[:4],
            en_keywords[:4],
            len(related_news),
            len(overseas_news),
        )

    return (
        {
            "name": name,
            "handle": channel["handle"],
            "channel_id": channel_info.get("channel_id", channel.get("channel_id", "")),
            "videos": video_results,
        },
        weighted_keywords,
    )


def build_en_profile(profile_ja: dict[str, float]) -> dict[str, float]:
    """日本語の関心プロファイルを英訳し、固定のシードキーワードで補完する。"""
    profile_en: dict[str, float] = {}
    for word, weight in profile_ja.items():
        en = translator.translate_keyword(word)
        if en:
            profile_en[en] = max(profile_en.get(en, 0.0), weight)
    for seed in INTEREST_SEED_KEYWORDS_EN:
        profile_en.setdefault(seed, 0.4)
    return profile_en


def main() -> None:
    args = parse_args()

    feed_pool: list[dict] = []
    if not args.no_overseas:
        logger.info("海外ニュースサイトのRSSを取得中...")
        feed_pool = fetch_overseas_feeds()
        logger.info("  海外記事候補: %d件", len(feed_pool))

    by_channel = []
    all_weighted: list[tuple[list[str], float]] = []
    for channel in CHANNELS:
        channel_result, weighted = collect_for_channel(channel, args.max_videos, feed_pool, args)
        by_channel.append(channel_result)
        all_weighted.extend(weighted)

    profile_ja = build_weighted_profile(all_weighted)
    logger.info("関心キーワードプロファイル: %s", list(profile_ja)[:15])

    general_trends = []
    if not args.no_domestic:
        logger.info("国内トレンドニュース収集中...")
        general_trends = collect_general_trends(list(profile_ja))

    profile_en: dict[str, float] = {}
    overseas_trends: list[dict] = []
    japan_in_overseas: list[dict] = []
    if not args.no_overseas:
        profile_en = build_en_profile(profile_ja)
        logger.info("海外トレンドニュース収集中...")
        overseas_trends = collect_overseas_trends(feed_pool, profile_en)
        japan_in_overseas = collect_japan_in_overseas(feed_pool)
        translator.save_cache()

    result = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "channels": [{"name": c["name"], "handle": c["handle"]} for c in by_channel],
        "by_channel": by_channel,
        "keyword_profile": profile_ja,
        "keyword_profile_en": profile_en,
        "general_trends": general_trends,
        "overseas_trends": overseas_trends,
        "japan_in_overseas": japan_in_overseas,
    }

    json_path, md_path = write_report(result, args.output_dir)
    logger.info("レポート出力完了: %s / %s", json_path, md_path)


if __name__ == "__main__":
    main()
