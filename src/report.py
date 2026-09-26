"""収集結果をMarkdown / JSONレポートとして出力するモジュール。"""

from __future__ import annotations

import json
import os
from datetime import datetime

_CATEGORY_LABELS = {
    "world": "国際",
    "us_politics": "米国政治・社会",
    "business": "経済",
    "tech": "IT",
    "entertainment": "エンタメ",
    "sports": "スポーツ",
    "japan": "日本",
    "asia": "アジア",
    "search": "検索",
}


def _fmt_article_line(article: dict, score_key: str | None = None) -> str:
    source = f" - {article['source']}" if article.get("source") else ""
    date = f" ({article['published_at'][:16]})" if article.get("published_at") else ""
    score = ""
    if score_key and article.get(score_key) is not None:
        score = f" [score: {article[score_key]}]"
    return f"- [{article['title']}]({article['link']}){source}{date}{score}"


def _fmt_overseas_line(article: dict, score_key: str) -> str:
    line = _fmt_article_line(article, score_key)
    tags = []
    if article.get("category") in _CATEGORY_LABELS:
        tags.append(_CATEGORY_LABELS[article["category"]])
    if article.get("coverage", 1) > 1:
        tags.append(f"{article['coverage']}媒体が報道")
    if article.get("matched_keywords"):
        tags.append("関心語: " + ", ".join(article["matched_keywords"][:4]))
    if tags:
        line += " _[" + " / ".join(tags) + "]_"
    return line


def _fmt_count(value) -> str:
    return f"{value:,}" if isinstance(value, int) else "-"


def build_markdown_report(result: dict) -> str:
    lines: list[str] = []
    add = lines.append
    add(f"# ニュース自動収集レポート ({result['generated_at']})")
    add("")
    add("対象チャンネル: " + ", ".join(f"{c['name']} ({c['handle']})" for c in result["channels"]))
    add("")

    # --- 1. 動画関連 ---
    add("## 1. 動画に関連する最新ニュース (国内・海外)")
    add("")
    for ch in result["by_channel"]:
        add(f"### {ch['name']} ({ch['handle']})")
        add("")
        if not ch["videos"]:
            add("_動画情報を取得できませんでした (チャンネルIDまたはYOUTUBE_API_KEYを確認してください)_")
            add("")
            continue
        for v in ch["videos"]:
            add(f"#### 動画: [{v['title']}]({v['url']})")
            add(
                f"- 公開日: {v['published_at'][:10]} / 再生数: {_fmt_count(v.get('view_count'))}"
                f" / 高評価: {_fmt_count(v.get('like_count'))} / 視聴者関心度: x{v.get('interest_weight', 1)}"
            )
            add(f"- キーワード: {', '.join(v['keywords']) or '(なし)'}")
            if v.get("keywords_en"):
                add(f"- 英訳キーワード: {', '.join(v['keywords_en'])}")
            if v.get("comment_keywords"):
                add(f"- 視聴者コメントの頻出語: {', '.join(v['comment_keywords'])}")
            if v.get("related_news"):
                add("- 国内の関連ニュース:")
                for a in v["related_news"]:
                    add("  " + _fmt_article_line(a, "relevance_score"))
            if v.get("overseas_news"):
                add("- 海外の関連ニュース:")
                for a in v["overseas_news"]:
                    add("  " + _fmt_article_line(a, "relevance_score"))
            if not v.get("related_news") and not v.get("overseas_news"):
                add("- 関連ニュース: 見つかりませんでした")
            add("")

    # --- 2. 海外トレンド ---
    add("## 2. 海外で話題 × 視聴者が興味を持ちそうなニュース")
    add("")
    add(
        "海外ニュースサイトの最新記事を「両チャンネルの視聴者の関心 (再生数で重み付けした動画テーマ・"
        "コメント・定番テーマ)」「何媒体が同時に報じているか」「鮮度」でスコアリングしています。"
    )
    add("")
    for a in result.get("overseas_trends", []):
        add(_fmt_overseas_line(a, "interest_score"))
    if not result.get("overseas_trends"):
        add("(データなし)")
    add("")

    # --- 3. 海外が報じる日本 ---
    add("## 3. 海外メディアが報じる日本")
    add("")
    for a in result.get("japan_in_overseas", []):
        add(_fmt_overseas_line(a, "interest_score"))
    if not result.get("japan_in_overseas"):
        add("(データなし)")
    add("")

    # --- 4. 国内トレンド ---
    add("## 4. 国内で話題 × 視聴者が興味を持ちそうなニュース")
    add("")
    for a in result.get("general_trends", []):
        add(_fmt_article_line(a, "interest_score") + f" _[{a.get('category', '')}]_")
    if not result.get("general_trends"):
        add("(データなし)")
    add("")

    # --- 5. プロファイル ---
    add("## 5. 視聴者の関心キーワードプロファイル")
    add("")
    profile = result.get("keyword_profile") or {}
    add("- 日本語: " + (", ".join(f"{k}({w})" for k, w in profile.items()) or "(データなし)"))
    profile_en = result.get("keyword_profile_en") or {}
    if profile_en:
        add("- 英語 (海外ニュース照合用): " + ", ".join(f"{k}({w})" for k, w in profile_en.items()))
    add("")

    return "\n".join(lines)


def write_report(result: dict, output_dir: str) -> tuple[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    markdown = build_markdown_report(result)
    json_text = json.dumps(result, ensure_ascii=False, indent=2)

    json_path = os.path.join(output_dir, f"news_report_{timestamp}.json")
    md_path = os.path.join(output_dir, f"news_report_{timestamp}.md")
    for path, text in (
        (json_path, json_text),
        (md_path, markdown),
        (os.path.join(output_dir, "latest.json"), json_text),
        (os.path.join(output_dir, "latest.md"), markdown),
    ):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    return json_path, md_path
