"""海外ニュース収集・YouTube RSS・翻訳・関心プロファイルのオフラインテスト。"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import overseas_news, translator
from src.overseas_news import (
    annotate_coverage,
    collect_overseas_for_video,
    collect_overseas_trends,
    filter_recent,
    is_japan_related,
    keyword_in_text,
    parse_feed,
    recency_factor,
)
from src.relevance import build_weighted_profile, video_weights
from src.youtube_collector import parse_channel_feed

NOW = datetime.now(timezone.utc)
RECENT = NOW.strftime("%a, %d %b %Y %H:%M:%S +0000")

RSS = f"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>BBC</title>
<item><title>Trump announces new tariffs on China</title><link>https://bbc.example/1</link>
<description>&lt;p&gt;The White House said...&lt;/p&gt;</description><pubDate>{RECENT}</pubDate></item>
<item><title>Old story</title><link>https://bbc.example/2</link><pubDate>Mon, 01 Jan 2024 00:00:00 +0000</pubDate></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Verge</title>
<entry><title>Sony unveils new console in Tokyo</title><link rel="alternate" href="https://verge.example/a"/>
<published>2026-09-25T10:00:00Z</published><summary>Japanese giant...</summary></entry>
</feed>"""

RDF = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
<item><title>Germany election result</title><link>https://dw.example/x</link><dc:date>2026-09-25T08:00:00Z</dc:date></item>
</rdf:RDF>"""

GOOGLE_NEWS_ITEM = """<?xml version="1.0"?><rss><channel>
<item><title>Disney stock falls after boycott - Reuters</title><link>https://news.google.com/x</link>
<source url="https://reuters.com">Reuters</source><pubDate>Fri, 25 Sep 2026 09:30:34 GMT</pubDate></item>
</channel></rss>"""

YT_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/"
 xmlns="http://www.w3.org/2005/Atom">
 <yt:channelId>UCe3SZWQT_t4fgf6CrsAf_ow</yt:channelId>
 <title>プク太の世界時事ニュース</title>
 <entry>
  <yt:videoId>abc123</yt:videoId>
  <title>ディズニー新作が大コケ！ハリウッドのポリコレ路線に批判殺到</title>
  <published>2026-09-20T09:00:00+00:00</published>
  <media:group>
   <media:description>今回はディズニーの話題です</media:description>
   <media:community>
    <media:starRating count="1500" average="5.00" min="1" max="5"/>
    <media:statistics views="120000"/>
   </media:community>
  </media:group>
 </entry>
</feed>"""


class FeedParserTest(unittest.TestCase):
    def test_rss2(self):
        items = parse_feed(RSS, "BBC News")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["source"], "BBC News")
        self.assertEqual(items[0]["summary"], "The White House said...")

    def test_atom(self):
        items = parse_feed(ATOM, "The Verge")
        self.assertEqual(items[0]["link"], "https://verge.example/a")
        self.assertTrue(items[0]["published_at"].startswith("2026-09-25T10:00"))

    def test_rdf(self):
        items = parse_feed(RDF, "DW")
        self.assertEqual(items[0]["title"], "Germany election result")

    def test_google_news_source_suffix_removed(self):
        items = parse_feed(GOOGLE_NEWS_ITEM)
        self.assertEqual(items[0]["title"], "Disney stock falls after boycott")
        self.assertEqual(items[0]["source"], "Reuters")

    def test_broken_xml_returns_empty(self):
        self.assertEqual(parse_feed("<rss><broken", "x"), [])

    def test_filter_recent_drops_old_articles(self):
        items = filter_recent(parse_feed(RSS, "BBC"))
        self.assertEqual([a["link"] for a in items], ["https://bbc.example/1"])


class ScoringTest(unittest.TestCase):
    def test_keyword_word_boundary(self):
        self.assertTrue(keyword_in_text("AI", "New AI rules in EU"))
        self.assertFalse(keyword_in_text("AI", "Said the chairman"))
        self.assertTrue(keyword_in_text("xi jinping", "Xi Jinping meets Trump"))

    def test_japan_related(self):
        self.assertTrue(is_japan_related({"title": "Tokyo stocks rally", "summary": ""}))
        self.assertFalse(is_japan_related({"title": "Paris fashion week", "summary": ""}))

    def test_coverage_counts_distinct_sources(self):
        articles = [
            {"title": "Israel strikes Gaza hospital killing dozens", "source": "BBC"},
            {"title": "Israel strikes Gaza hospital, dozens killed", "source": "Al Jazeera"},
            {"title": "Apple releases new iPhone models today", "source": "Verge"},
        ]
        result = annotate_coverage(articles)
        self.assertEqual(result[0]["coverage"], 2)
        self.assertEqual(result[2]["coverage"], 1)

    def test_recency_factor(self):
        self.assertEqual(recency_factor(NOW.isoformat()), 1.0)
        old = (NOW - timedelta(days=7)).isoformat()
        self.assertLess(recency_factor(old), 0.7)
        self.assertEqual(recency_factor(""), 0.8)

    def test_overseas_for_video_uses_feed_pool(self):
        pool = [
            {"title": "Disney box office flop sparks debate", "link": "1", "source": "Variety", "summary": "", "published_at": NOW.isoformat(), "category": "entertainment"},
            {"title": "Unrelated weather story", "link": "2", "source": "BBC", "summary": "", "published_at": NOW.isoformat(), "category": "world"},
        ]
        result = collect_overseas_for_video(["Disney", "Hollywood"], pool, search=False)
        self.assertEqual([a["link"] for a in result], ["1"])
        self.assertAlmostEqual(result[0]["relevance_score"], 0.5)

    def test_overseas_trends_prefers_viewer_interest(self):
        pool = [
            {"title": "Local council approves new park", "link": "a", "source": "BBC", "summary": "", "published_at": NOW.isoformat(), "category": "world"},
            {"title": "Trump signs order on transgender athletes", "link": "b", "source": "Fox News", "summary": "", "published_at": NOW.isoformat(), "category": "us_politics"},
        ]
        result = collect_overseas_trends(pool, {"Trump": 1.0, "transgender": 0.6})
        self.assertEqual(result[0]["link"], "b")
        self.assertEqual(set(result[0]["matched_keywords"]), {"Trump", "transgender"})

    def test_japan_in_overseas_excludes_japanese_outlets(self):
        pool = [
            {"title": "Japan PM visits Washington", "link": "a", "source": "BBC News", "summary": "", "published_at": NOW.isoformat()},
            {"title": "Japan PM visits Washington today", "link": "b", "source": "The Japan Times", "summary": "", "published_at": NOW.isoformat()},
        ]
        with mock.patch.object(overseas_news, "search_overseas_news", return_value=[]):
            result = overseas_news.collect_japan_in_overseas(pool)
        self.assertEqual([a["link"] for a in result], ["a"])


class YouTubeFeedTest(unittest.TestCase):
    def test_parse_channel_feed_with_stats(self):
        channel, videos = parse_channel_feed(YT_FEED)
        self.assertEqual(channel["channel_id"], "UCe3SZWQT_t4fgf6CrsAf_ow")
        self.assertEqual(channel["title"], "プク太の世界時事ニュース")
        self.assertEqual(videos[0]["view_count"], 120000)
        self.assertEqual(videos[0]["like_count"], 1500)
        self.assertEqual(videos[0]["description"], "今回はディズニーの話題です")


class ProfileTest(unittest.TestCase):
    def test_video_weights_relative_to_median(self):
        videos = [{"view_count": 1000}, {"view_count": 10000}, {"view_count": 100}]
        self.assertEqual(video_weights(videos), [1.0, 3.0, 0.5])

    def test_video_weights_without_stats(self):
        self.assertEqual(video_weights([{}, {}]), [1.0, 1.0])

    def test_weighted_profile_normalized(self):
        profile = build_weighted_profile([(["ディズニー", "ハリウッド"], 3.0), (["関税"], 1.0)])
        self.assertEqual(profile["ディズニー"], 1.0)
        self.assertAlmostEqual(profile["関税"], 0.333, places=3)


class TranslatorTest(unittest.TestCase):
    def test_dictionary_and_ascii(self):
        with mock.patch.object(translator, "_lookup_wikipedia", side_effect=AssertionError("no network")):
            self.assertEqual(translator.translate_keyword("ハリウッド"), "Hollywood")
            self.assertEqual(translator.translate_keyword("NATO"), "NATO")

    def test_wikipedia_fallback_and_dedupe(self):
        translator._cache = {}
        with mock.patch.object(translator, "_lookup_wikipedia", return_value="Shohei Ohtani") as m:
            result = translator.translate_keywords(["大谷翔平", "大谷翔平", "トランプ", "トランプ大統領"])
        self.assertEqual(result, ["Shohei Ohtani", "Trump"])
        m.assert_called_once_with("大谷翔平")

    def test_clean_en_title(self):
        self.assertEqual(translator._clean_en_title("Mercury (planet)"), "Mercury")


if __name__ == "__main__":
    unittest.main()
