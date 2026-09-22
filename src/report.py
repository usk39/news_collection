"""収集結果をMarkdown / JSONレポートとして出力するモジュール。"""

from __future__ import annotations

import json
import os
from datetime import datetime


def _fmt_article_line(article: dict, score_key: str | None = None) -> str:
    source = f" - {article['source']}" if article.get("source") else ""
    date = f" ({article['published_at']})" if article.get("published_at") else ""
    score = ""
    if score_key and article.get(score_key) is not None:
        score = f" [score: {article[score_key]}]"
    return f"- [{article['title']}]({article['link']}){source}{date}{score}"


def build_markdown_report(result: dict) -> str:
    lines = []
    generated_at = result["generated_at"]
    lines.append(f"# ニュース自動収集レポート ({generated_at})")
    lines.append("")
    lines.append(
        "対象チャンネル: "
        + ", ".join(f"{c['name']} ({c['handle']})" for c in result["channels"])
    )
    lines.append("")
    lines.append("## 1. 動画に関連する最新ニュース")
    lines.append("")

    for channel_result in result["by_channel"]:
        lines.append(f"### {channel_result['name']} ({channel_result['handle']})")
        lines.append("")
        if not channel_result["videos"]:
            lines.append("_動画情報を取得できませんでした (YOUTUBE_API_KEY未設定の可能性があります)_")
            lines.append("")
            continue

        for video in channel_result["videos"]:
            lines.append(f"#### 動画: [{video['title']}]({video['url']})")
            lines.append(f"- 公開日: {video['published_at']}")
            lines.append(f"- 抽出キーワード: {', '.join(video['keywords']) or '(なし)'}")
            if video["related_news"]:
                lines.append("- 関連ニュース:")
                for article in video["related_news"]:
                    lines.append("  " + _fmt_article_line(article, "relevance_score"))
            else:
                lines.append("- 関連ニュース: 見つかりませんでした")
            lines.append("")

    lines.append("## 2. 視聴者が関心を持ちそうな一般トレンドニュース")
    lines.append("")
    lines.append(
        "両チャンネルの過去動画テーマとの関連度、およびニュースカテゴリの重みでスコアリングした"
        "一般トレンドニュース一覧です。"
    )
    lines.append("")
    for article in result["general_trends"]:
        lines.append(_fmt_article_line(article, "interest_score") + f" _[{article.get('category', '')}]_")

    lines.append("")
    lines.append("## 3. チャンネル共通の関心キーワードプロファイル")
    lines.append("")
    lines.append(", ".join(result["keyword_profile"]) or "(データなし)")
    lines.append("")

    return "\n".join(lines)


def write_report(result: dict, output_dir: str) -> tuple[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = os.path.join(output_dir, f"news_report_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    md_path = os.path.join(output_dir, f"news_report_{timestamp}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(build_markdown_report(result))

    latest_md_path = os.path.join(output_dir, "latest.md")
    with open(latest_md_path, "w", encoding="utf-8") as f:
        f.write(build_markdown_report(result))

    return json_path, md_path
