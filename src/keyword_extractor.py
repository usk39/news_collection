"""動画タイトル・概要欄から検索キーワードを抽出するモジュール。

外部の形態素解析ライブラリ (janome / sudachipy 等) に依存せず、
正規表現ベースで「固有名詞になりやすい文字列」を抽出する軽量な実装。
- カタカナ連続 (人名・製品名・カタカナ語に多い)
- 漢字連続 (地名・組織名・熟語に多い)
- 英数字/アルファベット連続 (略語・企業名・製品名に多い)
- 「」『』で囲まれたフレーズ (動画タイトルで固有名詞を強調する際によく使われる)

janome がインストールされている場合は、より精度の高い名詞抽出を優先的に使う。
"""

from __future__ import annotations

import re
from collections import Counter

from config import STOPWORDS

try:
    from janome.tokenizer import Tokenizer as _JanomeTokenizer

    _janome_tokenizer = _JanomeTokenizer()
except Exception:  # pragma: no cover - janome is an optional dependency
    _janome_tokenizer = None

_URL_RE = re.compile(r"https?://\S+")
_HASHTAG_RE = re.compile(r"[#＃](\S+)")
_BRACKET_RE = re.compile(r"[「『【\[]([^」』】\]]{2,20})[」』】\]]")
_KATAKANA_RE = re.compile(r"[ァ-ヴー]{2,}")
_KANJI_RE = re.compile(r"[一-龥]{2,}")
_ALNUM_RE = re.compile(r"[A-Za-zＡ-Ｚａ-ｚ0-9]{2,}")


def _clean_text(text: str) -> str:
    text = _URL_RE.sub(" ", text or "")
    return text


def _extract_with_janome(text: str) -> list[str]:
    """janome が使える場合、名詞(一般/固有名詞/サ変接続)を抽出する。"""
    candidates = []
    for token in _janome_tokenizer.tokenize(text):
        pos = token.part_of_speech.split(",")
        if pos[0] != "名詞":
            continue
        if pos[1] in {"代名詞", "非自立", "数"}:
            continue
        surface = token.base_form if token.base_form != "*" else token.surface
        if len(surface) < 2:
            continue
        candidates.append(surface)
    return candidates


def _extract_with_regex(text: str) -> list[str]:
    candidates: list[str] = []
    candidates += _BRACKET_RE.findall(text)
    candidates += _HASHTAG_RE.findall(text)
    candidates += _KATAKANA_RE.findall(text)
    candidates += _KANJI_RE.findall(text)
    candidates += _ALNUM_RE.findall(text)
    return candidates


def extract_keywords(title: str, description: str = "", max_keywords: int = 8) -> list[str]:
    """タイトルと概要欄からキーワード候補を抽出し、頻度順に上位を返す。

    タイトルに出現した語は概要欄の語より重み(出現回数換算)を大きくする。
    """
    title = _clean_text(title)
    description = _clean_text(description)

    if _janome_tokenizer is not None:
        title_words = _extract_with_janome(title)
        desc_words = _extract_with_janome(description)
    else:
        title_words = _extract_with_regex(title)
        desc_words = _extract_with_regex(description)

    counter: Counter[str] = Counter()
    for w in title_words:
        counter[w] += 3
    for w in desc_words:
        counter[w] += 1

    ranked = [
        word
        for word, _ in counter.most_common()
        if word not in STOPWORDS and not word.isdigit()
    ]

    # 重複や部分文字列の重複 (例: "岸田" と "岸田首相") を軽くまとめる
    deduped: list[str] = []
    for word in ranked:
        if any(word in other or other in word for other in deduped):
            continue
        deduped.append(word)
        if len(deduped) >= max_keywords:
            break

    return deduped


def build_query(keywords: list[str], max_terms: int = 3) -> str:
    """Google News RSS 検索用のクエリ文字列を組み立てる (OR 検索)。"""
    terms = keywords[:max_terms]
    if not terms:
        return ""
    if len(terms) == 1:
        return terms[0]
    return " OR ".join(f'"{t}"' for t in terms)
