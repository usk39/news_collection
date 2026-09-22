"""ネットワークアクセスなしで検証できるコアロジックのユニットテスト。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.keyword_extractor import build_query, extract_keywords
from src.relevance import build_keyword_profile, dedupe_articles, score_by_keywords


class KeywordExtractorTest(unittest.TestCase):
    def test_extracts_bracketed_and_kanji_terms(self):
        title = "【速報】岸田政権が緊急会見！物価高騒動の裏側とは"
        desc = "今回は岸田首相が発表した経済対策について解説します。"
        keywords = extract_keywords(title, desc)
        self.assertIn("岸田政権", keywords)
        self.assertTrue(len(keywords) > 0)

    def test_stopwords_are_excluded(self):
        keywords = extract_keywords("今日の動画は解説です", "話題のニュースまとめ")
        for stop in ("今日", "動画", "解説", "話題", "ニュース", "まとめ"):
            self.assertNotIn(stop, keywords)

    def test_build_query_uses_or_syntax_for_multiple_terms(self):
        query = build_query(["岸田政権", "物価高"])
        self.assertEqual(query, '"岸田政権" OR "物価高"')

    def test_build_query_single_term(self):
        self.assertEqual(build_query(["岸田政権"]), "岸田政権")

    def test_build_query_empty(self):
        self.assertEqual(build_query([]), "")


class RelevanceTest(unittest.TestCase):
    def test_dedupe_by_link_and_title(self):
        articles = [
            {"title": "A", "link": "https://x/1"},
            {"title": "A", "link": "https://x/1"},
            {"title": "A", "link": "https://x/2"},
            {"title": "B", "link": "https://x/3"},
        ]
        deduped = dedupe_articles(articles)
        self.assertEqual(len(deduped), 2)

    def test_score_by_keywords(self):
        score = score_by_keywords("岸田首相が物価高対策を発表", ["岸田", "物価高", "存在しない語"])
        self.assertAlmostEqual(score, 2 / 3)

    def test_score_by_keywords_no_keywords(self):
        self.assertEqual(score_by_keywords("何かの記事", []), 0.0)

    def test_build_keyword_profile_ranks_by_frequency(self):
        profile = build_keyword_profile([["A", "B"], ["A", "C"], ["A"]])
        self.assertEqual(profile[0], "A")


if __name__ == "__main__":
    unittest.main()
