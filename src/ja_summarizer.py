"""Claude API で海外記事の見出しを日本語訳し、日本語の要約を付けるモジュール。

- ANTHROPIC_API_KEY が設定されているときだけ動作する (未設定なら何もしない)。
- 記事は複数件ずつまとめて1リクエストで処理し、構造化出力 (JSON Schema) で
  {id, title_ja, summary_ja} を受け取る。
- 結果は記事URLをキーにキャッシュし、毎日の実行で同じ記事を再翻訳しない。
- 要約は RSS に含まれる見出し・リード文だけを根拠に作らせる (本文は取得しない)。
"""

from __future__ import annotations

import json
import logging
import os

from config import (
    ANTHROPIC_API_KEY,
    CACHE_DIR,
    CLAUDE_EFFORT,
    CLAUDE_MODEL,
    JA_SUMMARY_BATCH_SIZE,
    JA_SUMMARY_MAX_ARTICLES,
)

logger = logging.getLogger(__name__)

_CACHE_PATH = os.path.join(CACHE_DIR, "ja_summaries.json")

SYSTEM_PROMPT = """\
あなたは海外ニュースを日本の視聴者向けに紹介する、プロの翻訳者兼ニュース編集者です。
時事ニュース解説YouTubeチャンネルの台本作成者が、海外記事をすばやく把握するために使います。

各記事について次を作成してください。
- title_ja: 見出しの自然な日本語訳。日本のニュースサイトの見出しのように簡潔に (40字程度まで)。
  人名・地名・組織名は日本の報道で一般的な表記にする (例: Xi Jinping → 習近平、White House → ホワイトハウス)。
- summary_ja: 記事の要点を日本語で2〜3文 (120字程度まで)。初めて聞く人にも分かるよう、
  必要なら「誰が」「どこで」を補う。

厳守事項:
- 与えられた見出しとリード文に書かれている内容だけを根拠にする。書かれていない数字・発言・背景・評価を付け足さない。
- リード文が無い、または情報が少ない場合は、見出しから読み取れる範囲だけを1文で書く。
- 記事の主張をそのまま事実と断定せず、「〜と報じている」「〜としている」など報道であることが分かる書き方にする。
- 入力に含まれるすべての id について、入力と同じ id で1件ずつ返す。
"""

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "title_ja": {"type": "string"},
                    "summary_ja": {"type": "string"},
                },
                "required": ["id", "title_ja", "summary_ja"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

_client = None
_cache: dict[str, dict] | None = None


def is_enabled() -> bool:
    return bool(ANTHROPIC_API_KEY)


def _get_client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _load_cache() -> dict[str, dict]:
    global _cache
    if _cache is None:
        try:
            with open(_CACHE_PATH, encoding="utf-8") as f:
                _cache = json.load(f)
        except (OSError, ValueError):
            _cache = {}
    return _cache


def save_cache() -> None:
    if _cache is None:
        return
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(_cache, f, ensure_ascii=False, indent=1, sort_keys=True)


def build_user_message(batch: list[dict]) -> str:
    payload = [
        {
            "id": i,
            "source": a.get("source", ""),
            "title": a.get("title", ""),
            "lead": a.get("summary", ""),
        }
        for i, a in enumerate(batch)
    ]
    return (
        "次の海外ニュース記事の見出しを日本語に訳し、要約を付けてください。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=1)
    )


def _translate_batch(batch: list[dict]) -> dict[int, dict]:
    """1バッチ分を Claude に送り、{id: {title_ja, summary_ja}} を返す。"""
    import anthropic

    client = _get_client()
    try:
        response = client.beta.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_message(batch)}],
            output_config={
                "effort": CLAUDE_EFFORT,
                "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA},
            },
            # 安全分類器による拒否時は、サーバー側で自動的に別モデルへフォールバックさせる
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError:
        logger.error("ANTHROPIC_API_KEY が無効です。日本語要約をスキップします。")
        raise
    except anthropic.RateLimitError as exc:
        logger.warning("Claude API のレート制限に達しました: %s", exc)
        return {}
    except anthropic.APIStatusError as exc:
        logger.warning("Claude API エラー (%s): %s", exc.status_code, exc.message)
        return {}
    except anthropic.APIConnectionError as exc:
        logger.warning("Claude API に接続できませんでした: %s", exc)
        return {}

    if response.stop_reason == "refusal":
        logger.warning("このバッチは翻訳を拒否されました (request_id=%s)", response._request_id)
        return {}
    if response.stop_reason == "max_tokens":
        logger.warning("出力が上限で途切れました。JA_SUMMARY_BATCH_SIZE を小さくしてください。")
        return {}

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        items = json.loads(text)["items"]
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("Claude の出力を解析できませんでした: %s", exc)
        return {}
    return {
        item["id"]: {"title_ja": item["title_ja"].strip(), "summary_ja": item["summary_ja"].strip()}
        for item in items
        if isinstance(item.get("id"), int) and 0 <= item["id"] < len(batch)
    }


def annotate_japanese(article_lists: list[list[dict]]) -> int:
    """複数の記事リストに title_ja / summary_ja を付与する (リスト内の dict を直接更新)。

    同じ記事 (URL) が複数リストに出てきても翻訳は1回だけ。戻り値は新たに翻訳した件数。
    """
    if not is_enabled():
        return 0

    cache = _load_cache()

    # 翻訳が必要な記事を、先頭 (スコア上位) から重複なく集める
    pending: dict[str, dict] = {}
    for articles in article_lists:
        for a in articles:
            link = a.get("link")
            if link and link not in cache and link not in pending:
                pending[link] = a
    targets = list(pending.values())[:JA_SUMMARY_MAX_ARTICLES]
    if len(pending) > len(targets):
        logger.info("日本語要約は上位 %d 件に制限します (候補 %d 件)", len(targets), len(pending))

    translated = 0
    for start in range(0, len(targets), JA_SUMMARY_BATCH_SIZE):
        batch = targets[start : start + JA_SUMMARY_BATCH_SIZE]
        try:
            results = _translate_batch(batch)
        except Exception as exc:  # 認証エラー等: 以降のバッチも失敗するので打ち切る
            logger.warning("日本語要約を中断しました: %s", exc)
            break
        for i, a in enumerate(batch):
            if i in results:
                cache[a["link"]] = results[i]
                translated += 1
        logger.info("  日本語要約: %d/%d 件完了", min(start + len(batch), len(targets)), len(targets))

    for articles in article_lists:
        for a in articles:
            hit = cache.get(a.get("link", ""))
            if hit:
                a.update(hit)

    save_cache()
    return translated
