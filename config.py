"""news_collection の設定値をまとめたモジュール。"""

import os

# ------------------------------------------------------------------
# 対象チャンネル
# ------------------------------------------------------------------
CHANNELS = [
    {"name": "すみおじじ", "handle": "@sumiaojiji"},
    {"name": "ぷくじじ", "handle": "@pukujiji"},
]

# ------------------------------------------------------------------
# YouTube Data API v3
# ------------------------------------------------------------------
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# 1チャンネルあたり直近何本の動画を対象にするか
MAX_VIDEOS_PER_CHANNEL = 15

# ------------------------------------------------------------------
# ニュース検索 (Google News RSS)
# ------------------------------------------------------------------
GOOGLE_NEWS_SEARCH_URL = "https://news.google.com/rss/search"
GOOGLE_NEWS_TOP_URL = "https://news.google.com/rss"
GOOGLE_NEWS_TOPIC_URL = "https://news.google.com/rss/headlines/section/topic/{topic}"

# 動画に紐づけるニュースを検索する際、何日以内の記事を対象にするか
NEWS_LOOKBACK_DAYS = 7

# 1動画あたり保持する関連ニュースの最大件数
MAX_NEWS_PER_VIDEO = 5

# 一般トレンドニュースとして保持する最大件数
MAX_GENERAL_TRENDS = 25

# 時事ニュースチャンネルの視聴者が関心を持ちやすいカテゴリ
# (Google News のトピックID。値は重み付けスコアの倍率)
TREND_TOPIC_WEIGHTS = {
    "NATION": 1.2,        # 社会
    "WORLD": 1.1,          # 国際
    "BUSINESS": 1.0,       # 経済
    "TECHNOLOGY": 1.0,     # IT・科学
    "ENTERTAINMENT": 0.8,  # エンタメ
    "SCIENCE": 0.9,        # 科学
}

# ------------------------------------------------------------------
# キーワード抽出用ストップワード
# ------------------------------------------------------------------
STOPWORDS = {
    "今日", "動画", "解説", "話題", "今回", "みんな", "チャンネル",
    "コメント", "登録", "高評価", "感想", "紹介", "最新", "速報",
    "とは", "について", "まとめ", "衝撃", "驚愕", "徹底", "検証",
    "その後", "現在", "本当", "実際", "理由", "なぜ", "一体",
    "日本", "海外", "世界", "ニュース", "問題", "事件", "事態",
}

# ------------------------------------------------------------------
# HTTP
# ------------------------------------------------------------------
HTTP_TIMEOUT = 15
USER_AGENT = "news-collection-bot/1.0 (+https://github.com/usk39/news_collection)"

OUTPUT_DIR = os.environ.get("NEWS_COLLECTION_OUTPUT_DIR", "output")
