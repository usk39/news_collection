"""news_collection の設定値をまとめたモジュール。"""

import os

try:  # .env があれば読み込む (python-dotenv は任意)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

# ------------------------------------------------------------------
# 対象チャンネル
# ------------------------------------------------------------------
# channel_id が分かっていれば指定しておくと、APIキーなしでもRSSで動画を取得できる。
# 空の場合はチャンネルページから自動解決を試みる。
# name はAPI/RSSで取得したチャンネル名があればそちらで上書きされる。
CHANNELS = [
    {"name": "すみれ＆あおいの時事ニュース", "handle": "@sumiaojiji", "channel_id": ""},
    {"name": "プク太の世界時事ニュース", "handle": "@pukujiji", "channel_id": "UCe3SZWQT_t4fgf6CrsAf_ow"},
]

# ------------------------------------------------------------------
# YouTube Data API v3
# ------------------------------------------------------------------
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

YOUTUBE_FEED_URL = "https://www.youtube.com/feeds/videos.xml"

# 1チャンネルあたり直近何本の動画を対象にするか
# (APIキーなしのRSSフォールバックでは最大15本)
MAX_VIDEOS_PER_CHANNEL = 15

# 視聴者コメントを取得する動画数・1動画あたりのコメント数 (APIキー必須)
COMMENT_VIDEOS_PER_CHANNEL = 5
MAX_COMMENTS_PER_VIDEO = 30

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
# 海外ニュース
# ------------------------------------------------------------------
# 英語版 Google News (キーワード検索に使用)。複数エディションを横断して検索する。
OVERSEAS_GOOGLE_NEWS_EDITIONS = [
    {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    {"hl": "en-GB", "gl": "GB", "ceid": "GB:en"},
]

# 海外ニュースサイトのRSSフィード。
# category は視聴者関心スコアの重み付けやレポートの表示に使う。
# (フィードURLは各社の都合で変わることがあるため、取得失敗時はログに警告を出してスキップする)
OVERSEAS_FEEDS = [
    # --- 国際総合 ---
    {"name": "BBC News", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "category": "world"},
    {"name": "The Guardian", "url": "https://www.theguardian.com/world/rss", "category": "world"},
    {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "category": "world"},
    {"name": "NPR", "url": "https://feeds.npr.org/1004/rss.xml", "category": "world"},
    {"name": "DW", "url": "https://rss.dw.com/rdf/rss-en-world", "category": "world"},
    {"name": "France 24", "url": "https://www.france24.com/en/rss", "category": "world"},
    {"name": "ABC News (US)", "url": "https://abcnews.go.com/abcnews/internationalheadlines", "category": "world"},
    # --- 米国政治・社会 (トランプ政権/移民/ポリコレ論争など) ---
    {"name": "Fox News", "url": "https://moxie.foxnews.com/google-publisher/politics.xml", "category": "us_politics"},
    {"name": "New York Post", "url": "https://nypost.com/feed/", "category": "us_politics"},
    {"name": "Politico", "url": "https://rss.politico.com/politics-news.xml", "category": "us_politics"},
    {"name": "The Hill", "url": "https://thehill.com/news/feed/", "category": "us_politics"},
    # --- 経済・テック ---
    {"name": "BBC Business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml", "category": "business"},
    {"name": "CNBC", "url": "https://www.cnbc.com/id/100727362/device/rss/rss.html", "category": "business"},
    {"name": "BBC Technology", "url": "https://feeds.bbci.co.uk/news/technology/rss.xml", "category": "tech"},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "category": "tech"},
    # --- ハリウッド・エンタメ・スポーツ ---
    {"name": "Deadline", "url": "https://deadline.com/feed/", "category": "entertainment"},
    {"name": "Variety", "url": "https://variety.com/feed/", "category": "entertainment"},
    {"name": "The Hollywood Reporter", "url": "https://www.hollywoodreporter.com/feed/", "category": "entertainment"},
    {"name": "BBC Sport", "url": "https://feeds.bbci.co.uk/sport/rss.xml", "category": "sports"},
    # --- アジア・日本 (海外メディアから見た日本) ---
    {"name": "The Japan Times", "url": "https://www.japantimes.co.jp/feed/", "category": "japan"},
    {"name": "NHK WORLD", "url": "https://www3.nhk.or.jp/rss/news/cat0.xml", "category": "japan"},
    {"name": "BBC Asia", "url": "https://feeds.bbci.co.uk/news/world/asia/rss.xml", "category": "asia"},
    {"name": "South China Morning Post", "url": "https://www.scmp.com/rss/91/feed", "category": "asia"},
]

# カテゴリごとの重み (時事ニュースチャンネルの視聴者が反応しやすいものを高めに)
OVERSEAS_CATEGORY_WEIGHTS = {
    "world": 1.1,
    "us_politics": 1.15,
    "japan": 1.2,
    "asia": 1.1,
    "business": 1.0,
    "tech": 0.95,
    "entertainment": 1.0,
    "sports": 0.8,
}

# 動画1本あたり保持する海外関連ニュースの最大件数
MAX_OVERSEAS_NEWS_PER_VIDEO = 5

# 「海外で話題・視聴者が興味を持ちそうなニュース」の保持件数
MAX_OVERSEAS_TRENDS = 30

# 「海外メディアが報じる日本」の保持件数
MAX_JAPAN_IN_OVERSEAS = 15

# 両チャンネルの視聴者が関心を持ちやすいテーマの英語シードキーワード。
# 動画から自動抽出したプロファイルに加えてスコアリングに使う。
# (プク太の世界時事ニュースで多く扱われる米国政治・ハリウッド・ポリコレ論争・中国情勢など)
INTEREST_SEED_KEYWORDS_EN = [
    "Trump", "White House", "election", "immigration", "border",
    "China", "Xi Jinping", "Taiwan", "Russia", "Ukraine", "Putin", "Israel", "Gaza", "Iran",
    "North Korea", "South Korea", "Japan", "tariff", "inflation",
    "Hollywood", "Disney", "Marvel", "Netflix", "box office", "Oscars",
    "woke", "DEI", "transgender", "free speech", "cancel culture", "boycott",
    "Elon Musk", "AI", "Olympics",
]

# 日本語キーワード → 英語の手動辞書 (Wikipedia で翻訳できない語や、訳を固定したい語)
KEYWORD_TRANSLATIONS = {
    "トランプ": "Trump",
    "トランプ大統領": "Trump",
    "バイデン": "Biden",
    "習近平": "Xi Jinping",
    "プーチン": "Putin",
    "ゼレンスキー": "Zelensky",
    "ネタニヤフ": "Netanyahu",
    "イーロン・マスク": "Elon Musk",
    "マスク氏": "Elon Musk",
    "ハリウッド": "Hollywood",
    "ディズニー": "Disney",
    "ポリコレ": "woke",
    "ポリティカル・コレクトネス": "political correctness",
    "トランスジェンダー": "transgender",
    "トランス女性": "transgender women",
    "移民": "immigration",
    "不法移民": "illegal immigration",
    "関税": "tariff",
    "物価高": "inflation",
    "円安": "yen weak",
    "中国": "China",
    "台湾": "Taiwan",
    "韓国": "South Korea",
    "北朝鮮": "North Korea",
    "ロシア": "Russia",
    "ウクライナ": "Ukraine",
    "イスラエル": "Israel",
    "ガザ": "Gaza",
    "イラン": "Iran",
    "アメリカ": "United States",
    "米国": "United States",
    "イギリス": "Britain",
    "英国": "Britain",
    "日本": "Japan",
    "首相": "prime minister",
    "大統領": "president",
    "選挙": "election",
}

# 翻訳結果などのキャッシュ保存先
CACHE_DIR = os.environ.get("NEWS_COLLECTION_CACHE_DIR", "cache")
WIKIPEDIA_API_URL = "https://ja.wikipedia.org/w/api.php"

# ------------------------------------------------------------------
# HTTP
# ------------------------------------------------------------------
HTTP_TIMEOUT = 15
USER_AGENT = "news-collection-bot/1.0 (+https://github.com/usk39/news_collection)"

OUTPUT_DIR = os.environ.get("NEWS_COLLECTION_OUTPUT_DIR", "output")
