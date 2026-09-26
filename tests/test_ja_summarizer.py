"""Claude API による日本語訳・要約のオフラインテスト (API はモックする)。"""

import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import ja_summarizer
from src.report import build_markdown_report


def _response(items, stop_reason="end_turn"):
    text = json.dumps({"items": items}, ensure_ascii=False)
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)],
        _request_id="req_test",
    )


class FakeClient:
    """messages.create の呼び出しを記録し、入力の各記事に訳を返すフェイク。"""

    def __init__(self, stop_reason="end_turn"):
        self.calls = []
        self.stop_reason = stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        payload = json.loads(kwargs["messages"][0]["content"].split("\n\n", 1)[1])
        items = [
            {"id": p["id"], "title_ja": f"訳:{p['title']}", "summary_ja": f"要約:{p['title']}"}
            for p in payload
        ]
        return _response(items, self.stop_reason)


class JaSummarizerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patches = [
            mock.patch.object(ja_summarizer, "ANTHROPIC_API_KEY", "sk-test"),
            mock.patch.object(ja_summarizer, "_CACHE_PATH", os.path.join(self.tmp.name, "c.json")),
            mock.patch.object(ja_summarizer, "CACHE_DIR", self.tmp.name),
            mock.patch.object(ja_summarizer, "_cache", None),
            mock.patch.object(ja_summarizer, "JA_SUMMARY_BATCH_SIZE", 2),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def _articles(self, *names):
        return [{"title": n, "link": f"https://x/{n}", "source": "BBC", "summary": ""} for n in names]

    def test_disabled_without_api_key(self):
        with mock.patch.object(ja_summarizer, "ANTHROPIC_API_KEY", ""):
            self.assertEqual(ja_summarizer.annotate_japanese([self._articles("A")]), 0)

    def test_translates_in_batches_and_dedupes_across_lists(self):
        trends = self._articles("A", "B", "C")
        video = [dict(trends[0])]  # 同じ記事が別リストにも出てくる
        fake = FakeClient()
        with mock.patch.object(ja_summarizer, "_client", fake):
            count = ja_summarizer.annotate_japanese([trends, video])
        self.assertEqual(count, 3)
        self.assertEqual(len(fake.calls), 2)  # 3件 / バッチ2件 = 2リクエスト
        self.assertEqual(trends[1]["title_ja"], "訳:B")
        self.assertEqual(video[0]["summary_ja"], "要約:A")

        call = fake.calls[0]
        self.assertEqual(call["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(call["fallbacks"], "default")
        self.assertIn("server-side-fallback-2026-07-01", call["betas"])

    def test_uses_cache_on_second_run(self):
        fake = FakeClient()
        with mock.patch.object(ja_summarizer, "_client", fake):
            ja_summarizer.annotate_japanese([self._articles("A")])
            ja_summarizer._cache = None  # キャッシュファイルから読み直させる
            again = self._articles("A")
            count = ja_summarizer.annotate_japanese([again])
        self.assertEqual(count, 0)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(again[0]["title_ja"], "訳:A")

    def test_max_articles_limit(self):
        fake = FakeClient()
        with mock.patch.object(ja_summarizer, "_client", fake), mock.patch.object(
            ja_summarizer, "JA_SUMMARY_MAX_ARTICLES", 1
        ):
            arts = self._articles("A", "B")
            self.assertEqual(ja_summarizer.annotate_japanese([arts]), 1)
        self.assertIn("title_ja", arts[0])
        self.assertNotIn("title_ja", arts[1])

    def test_refusal_leaves_articles_untranslated(self):
        fake = FakeClient(stop_reason="refusal")
        arts = self._articles("A")
        with mock.patch.object(ja_summarizer, "_client", fake):
            self.assertEqual(ja_summarizer.annotate_japanese([arts]), 0)
        self.assertNotIn("title_ja", arts[0])

    def test_ignores_out_of_range_ids(self):
        fake = FakeClient()
        fake.beta.messages.create = lambda **kw: _response(
            [{"id": 5, "title_ja": "x", "summary_ja": "y"}, {"id": 0, "title_ja": "訳", "summary_ja": "要"}]
        )
        arts = self._articles("A")
        with mock.patch.object(ja_summarizer, "_client", fake):
            self.assertEqual(ja_summarizer.annotate_japanese([arts]), 1)
        self.assertEqual(arts[0]["title_ja"], "訳")

    def test_prompt_contains_lead_text(self):
        msg = ja_summarizer.build_user_message(
            [{"title": "T", "summary": "Lead text", "source": "BBC", "link": "l"}]
        )
        self.assertIn('"lead": "Lead text"', msg)


class ReportJapaneseTest(unittest.TestCase):
    def test_report_shows_japanese_title_original_and_summary(self):
        article = {
            "title": "Trump signs order",
            "title_ja": "トランプ氏が大統領令に署名",
            "summary_ja": "米ホワイトハウスは…と発表したと報じている。",
            "link": "https://x/1",
            "source": "Fox News",
            "published_at": "2026-09-25T10:00:00+00:00",
            "interest_score": 2.0,
            "category": "us_politics",
            "coverage": 3,
        }
        result = {
            "generated_at": "now",
            "channels": [],
            "by_channel": [],
            "overseas_trends": [article],
        }
        md = build_markdown_report(result)
        self.assertIn("- **[トランプ氏が大統領令に署名](https://x/1)** - Fox News", md)
        self.assertIn("_[米国政治・社会 / 3媒体が報道]_\n  - 原題: Trump signs order", md)
        self.assertIn("  - 要約: 米ホワイトハウスは", md)


if __name__ == "__main__":
    unittest.main()
