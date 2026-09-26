"""日本語キーワードを海外ニュース検索用の英語キーワードに変換するモジュール。

有料の翻訳APIを使わずに、ニュースで重要な「固有名詞」を高精度に英訳するため
次の順で変換を試みる。
1. config.KEYWORD_TRANSLATIONS (手動辞書)
2. 英数字だけの語はそのまま (例: "NATO", "iPhone")
3. 日本語版 Wikipedia の言語間リンク (ja → en)。人名・地名・組織名・事件名に強い。

変換結果はキャッシュファイルに保存し、同じ語で何度もAPIを叩かないようにする。
訳せなかった語は None を返し、海外検索には使わない。
"""

from __future__ import annotations

import json
import logging
import os
import re

import requests

from config import CACHE_DIR, HTTP_TIMEOUT, KEYWORD_TRANSLATIONS, USER_AGENT, WIKIPEDIA_API_URL

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})

_ASCII_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .&'\-]*$")
_PAREN_RE = re.compile(r"\s*\(.*?\)\s*$")
_CACHE_PATH = os.path.join(CACHE_DIR, "translations.json")

_cache: dict[str, str | None] | None = None


def _load_cache() -> dict[str, str | None]:
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


def _clean_en_title(title: str) -> str:
    # "Mercury (planet)" → "Mercury" のような曖昧さ回避の括弧を除く
    return _PAREN_RE.sub("", title).strip()


def _lookup_wikipedia(word: str) -> str | None:
    params = {
        "action": "query",
        "titles": word,
        "prop": "langlinks",
        "lllang": "en",
        "redirects": 1,
        "format": "json",
        "formatversion": 2,
    }
    try:
        resp = _session.get(WIKIPEDIA_API_URL, params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", [])
    except (requests.RequestException, ValueError) as exc:
        logger.debug("Wikipedia 翻訳に失敗 (%s): %s", word, exc)
        return None
    for page in pages:
        for link in page.get("langlinks", []):
            title = _clean_en_title(link.get("title") or "")
            # 長すぎる記事名 (例: "List of ...") は検索語として使いにくいので採用しない
            if title and len(title.split()) <= 4 and not title.startswith("List of"):
                return title
    return None


def translate_keyword(word: str) -> str | None:
    """日本語キーワード1語を英語に変換する。変換できなければ None。"""
    word = (word or "").strip()
    if not word:
        return None
    if word in KEYWORD_TRANSLATIONS:
        return KEYWORD_TRANSLATIONS[word]
    if _ASCII_RE.match(word):
        return word
    cache = _load_cache()
    if word in cache:
        return cache[word]
    en = _lookup_wikipedia(word)
    cache[word] = en
    return en


def translate_keywords(words: list[str]) -> list[str]:
    """キーワードリストを英訳し、重複を除いて順序を保ったまま返す。"""
    result: list[str] = []
    seen: set[str] = set()
    for w in words:
        en = translate_keyword(w)
        if en and en.lower() not in seen:
            seen.add(en.lower())
            result.append(en)
    return result
