# news_collection

「すみれ＆あおいの時事ニュース」(`@sumiaojiji`) と「プク太の世界時事ニュース」(`@pukujiji`) の2つのYouTubeチャンネルを対象に、

1. **各チャンネルの動画で取り上げているテーマに関連するニュース** (国内 + **海外ニュースサイト**)
2. **両チャンネルの視聴者が興味を持ちそうな / 実際に興味を持っているニュース** (海外で話題のニュース・海外メディアが報じる日本・国内トレンド)

を自動で収集し、Markdown / JSON のレポートとして出力するツールです。台本作成 (すみれ・あおいの時事ニュース解説動画) のネタ探しを効率化することを目的としています。

## 仕組み

```
 YouTube (Data API v3 / APIキー無しならチャンネルRSS)
   │ 直近動画・再生数・高評価数・人気コメント
   ▼
 [キーワード抽出] ── 日本語キーワード ──▶ 日本語 Google News ──▶ 国内の関連ニュース
   │
   ├─ 英訳 (手動辞書 → Wikipedia言語間リンク) ──▶ 海外各社RSS + 英語版Google News(US/GB)
   │                                                 ──▶ 海外の関連ニュース
   ▼
 [視聴者関心プロファイル]
   = 動画テーマ × 再生数の重み + 人気コメントの頻出語 + 定番テーマ(シードキーワード)
   │
   ├─▶ 海外各社の最新記事をスコアリング ──▶ 海外で話題 × 視聴者が興味を持ちそうなニュース
   ├─▶ 日本に言及した海外記事を抽出     ──▶ 海外メディアが報じる日本
   └─▶ 日本語Google Newsの見出しをスコアリング ──▶ 国内トレンド
```

### 動画に関連するニュース
- 各動画のタイトル・概要欄からキーワードを抽出 (カタカナ語/漢字連続語/「」内フレーズなど。`janome` があれば形態素解析を優先)。
- **国内**: 日本語版 Google News RSS で直近1週間の記事を検索。
- **海外**: キーワードを英訳し、海外ニュースサイトのRSSと英語版 Google News (米国版・英国版) から関連記事を収集。
  - 英訳は ① `config.KEYWORD_TRANSLATIONS` (手動辞書) ② 英数字語はそのまま ③ 日本語版Wikipediaの言語間リンク の順で行います。人名・国名・組織名・事件名などニュースで重要な固有名詞に強く、APIキーも不要です。結果は `cache/translations.json` にキャッシュされます。

### 視聴者が興味を持ちそうな / 持っているニュース
「視聴者の関心プロファイル」を次の3つから作ります。
1. **動画テーマ × 再生数**: チャンネル内の再生数中央値に対する比率 (0.5〜3倍) で重み付け。よく再生された動画のテーマ = 視聴者が実際に興味を持っているテーマ。
2. **人気コメントの頻出語** (APIキー設定時): 再生数上位の動画のコメントから、視聴者が反応しているポイントを抽出。
3. **定番テーマ** (`config.INTEREST_SEED_KEYWORDS_EN`): 米国政治、中国・台湾、ハリウッド、ポリコレ/DEI論争、など両チャンネルで扱われやすいテーマ。

これを使い、海外各社の最新記事を次のスコアで並べます。

```
score = カテゴリ重み × (1 + 関心プロファイル一致度) × (1 + 報道媒体数ボーナス) × 鮮度
```

「報道媒体数」は似た見出しを何社が報じているかで、多くの海外メディアが同時に報じている = 国際的に大きなニュースとして上位に来ます。

### 収集対象の海外ニュースサイト (初期設定)

| 分野 | サイト |
| --- | --- |
| 国際総合 | BBC News, The Guardian, Al Jazeera, NPR, DW, France 24, ABC News |
| 米国政治・社会 | Fox News, New York Post, Politico, The Hill |
| 経済・IT | BBC Business, CNBC, BBC Technology, The Verge |
| ハリウッド・エンタメ・スポーツ | Deadline, Variety, The Hollywood Reporter, BBC Sport |
| アジア・日本 | The Japan Times, NHK WORLD, BBC Asia, South China Morning Post |
| 横断検索 | 英語版 Google News (US / GB) ※ Reuters, AP, NYT などもここ経由で拾えます |

`config.OVERSEAS_FEEDS` にRSSのURLを追加・削除するだけで対象サイトを変更できます。

## セットアップ

```bash
pip install -r requirements.txt
cp .env.example .env
# .env に YouTube Data API v3 のAPIキーを設定 (Google Cloud Consoleで発行)
```

YouTube Data API v3 のキーは [Google Cloud Console](https://console.cloud.google.com/apis/credentials) で発行できます (YouTube Data API v3 を有効化してください)。

`YOUTUBE_API_KEY` が未設定でも、YouTubeの公開RSSフィード (直近15本・再生数付き) で動画を取得して動作します。APIキーを設定すると、より多くの動画と人気コメントの分析まで行えます。

> ⚠️ APIキーは `.env` (git管理外) かGitHub ActionsのSecretsにだけ保存し、`.env.example` などコミットされるファイルには書かないでください。

## 使い方

```bash
python collect_news.py
# または
python collect_news.py --max-videos 10 --output-dir output
python collect_news.py --no-domestic   # 海外ニュースだけ収集
python collect_news.py --no-overseas   # 国内ニュースだけ収集
```

実行すると `output/` 配下に以下が生成されます。

- `news_report_<timestamp>.md` / `.json`: そのときの完全なレポート
- `latest.md` / `latest.json`: 最新レポートへの固定パス (Botや他ツールからの参照用)

レポートの構成:
1. 動画に関連する最新ニュース (国内・海外)
2. 海外で話題 × 視聴者が興味を持ちそうなニュース
3. 海外メディアが報じる日本
4. 国内で話題 × 視聴者が興味を持ちそうなニュース
5. 視聴者の関心キーワードプロファイル (日本語 / 英語)

## 対象チャンネル・パラメータの変更

`config.py` で以下を調整できます。

| 項目 | 説明 |
| --- | --- |
| `CHANNELS` | 対象チャンネルのハンドル・チャンネルID一覧 |
| `MAX_VIDEOS_PER_CHANNEL` | チャンネルごとに遡る動画数 |
| `NEWS_LOOKBACK_DAYS` | 動画関連ニュースの検索期間 (日) |
| `MAX_NEWS_PER_VIDEO` | 動画1本あたりの関連ニュース保持数 |
| `MAX_GENERAL_TRENDS` | 一般トレンドニュースの保持件数 |
| `TREND_TOPIC_WEIGHTS` | ニュースカテゴリごとの重み |
| `STOPWORDS` | キーワード抽出から除外する一般語 |
| `OVERSEAS_FEEDS` | 海外ニュースサイトのRSS一覧 (名前・URL・カテゴリ) |
| `OVERSEAS_CATEGORY_WEIGHTS` | 海外ニュースのカテゴリごとの重み |
| `OVERSEAS_GOOGLE_NEWS_EDITIONS` | 横断検索に使う英語版Google Newsのエディション |
| `INTEREST_SEED_KEYWORDS_EN` | 視聴者の定番関心テーマ (英語) |
| `KEYWORD_TRANSLATIONS` | 日本語→英語の手動翻訳辞書 (訳を固定したい語を追加) |
| `COMMENT_VIDEOS_PER_CHANNEL` / `MAX_COMMENTS_PER_VIDEO` | コメント分析の対象動画数・コメント数 |

## 定期自動実行 (GitHub Actions)

`.github/workflows/collect_news.yml` で毎日1回 (JST 22:00) 自動実行するワークフローを用意しています。

1. リポジトリの Settings → Secrets and variables → Actions に `YOUTUBE_API_KEY` を登録
2. ワークフローが自動実行され、`output/latest.md` / `latest.json` がリポジトリにコミットされます (翻訳キャッシュは Actions のキャッシュに保存) (手動実行は `workflow_dispatch` から可能)

ローカルの cron で動かす場合は以下のようなエントリでも実行できます。

```
0 22 * * * cd /path/to/news_collection && /usr/bin/python3 collect_news.py >> collect.log 2>&1
```

## ディレクトリ構成

```
news_collection/
├── collect_news.py        # エントリポイント
├── config.py               # 設定値
├── src/
│   ├── youtube_collector.py  # YouTube Data API / RSS 連携
│   ├── keyword_extractor.py  # タイトル/概要欄からキーワード抽出
│   ├── news_search.py        # 日本語 Google News RSS 検索
│   ├── overseas_news.py      # 海外ニュースサイト収集・スコアリング
│   ├── translator.py         # キーワード英訳 (辞書 + Wikipedia)
│   ├── trend_collector.py    # 国内トレンドニュース収集・スコアリング
│   ├── relevance.py          # 関連度スコアリング・関心プロファイル
│   └── report.py             # Markdown/JSONレポート生成
├── .github/workflows/collect_news.yml  # 定期自動実行
└── output/                 # 生成レポート (latest.md 以外はgit管理外)
```

## 制限事項・注意

- Google News RSS の仕様変更やアクセス制限により、取得できるニュース件数が変動することがあります。
- キーワード抽出は正規表現ベースの軽量実装のため、複雑な固有名詞や口語表現は取りこぼす場合があります。精度を上げたい場合は `janome` または `sudachipy` の導入を検討してください (`keyword_extractor.py` は `janome` があれば自動的に優先利用します)。
- 海外記事の英訳は固有名詞中心のため、「大コケ」のような口語は訳されず海外検索には使われません。訳を固定したい語は `KEYWORD_TRANSLATIONS` に追加してください。
- 海外ニュースサイトのRSS URLは各社の都合で変わることがあります。取得に失敗したフィードは警告ログを出してスキップされます。
- 実行環境からのアウトバウンドHTTPS通信 (YouTube / news.google.com / 各海外ニュースサイト / ja.wikipedia.org) が必要です。サンドボックス環境などでネットワークが制限されている場合は動作しません。
