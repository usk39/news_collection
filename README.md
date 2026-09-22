# news_collection

「すみおじじ」(`@sumiaojiji`) と「ぷくじじ」(`@pukujiji`) の2つのYouTubeチャンネルを対象に、

1. **各チャンネルの動画で取り上げられているテーマに関連するニュース**
2. **両チャンネルの視聴者が興味を持ちそうな一般トレンドニュース**

を自動で収集し、Markdown / JSON のレポートとして出力するツールです。台本作成 (すみれ・あおいの時事ニュース解説動画) のネタ探しを効率化することを目的としています。

## 仕組み

```
YouTube Data API v3          Google News RSS (キーワード無料検索)
  │ 直近の動画一覧               │ 動画キーワードに紐づくニュース
  ▼                             ▼
[動画タイトル/概要欄] ──キーワード抽出──▶ [関連ニュース検索] ──▶ 動画ごとの関連ニュース

  両チャンネル全動画のキーワード頻度
              │
              ▼
     [視聴者関心プロファイル] ──▶ Google Newsのトップ/カテゴリ別見出しをスコアリング
                                    ──▶ 視聴者が関心を持ちそうな一般トレンドニュース
```

- **動画関連ニュース**: 各動画のタイトル・概要欄からキーワードを抽出し (人名・固有名詞になりやすいカタカナ語/漢字連続語/「」内フレーズなどを正規表現で抽出、`janome` がインストールされていればそちらを優先)、Google News RSS 検索でここ1週間以内の関連記事を取得・スコアリングします。
- **一般トレンドニュース**: 両チャンネル分の動画キーワードを集計して「視聴者の関心プロファイル」を作成。Google Newsのトップストーリーとカテゴリ別見出し (社会・国際・経済・IT・エンタメ・科学) を取得し、カテゴリの重要度とプロファイルとの一致度でスコアリングして上位を抽出します。これにより「動画化していないが視聴者が反応しそうなニュース」も拾えます。

## セットアップ

```bash
pip install -r requirements.txt
cp .env.example .env
# .env に YouTube Data API v3 のAPIキーを設定 (Google Cloud Consoleで発行)
```

YouTube Data API v3 のキーは [Google Cloud Console](https://console.cloud.google.com/apis/credentials) で発行できます (YouTube Data API v3 を有効化してください)。

`YOUTUBE_API_KEY` が未設定の場合、動画に紐づく関連ニュース収集はスキップされますが、一般トレンドニュース収集 (視聴者が興味を持ちそうなニュース) はAPIキーなしでも動作します。

## 使い方

```bash
python collect_news.py
# または
python collect_news.py --max-videos 10 --output-dir output
```

実行すると `output/` 配下に以下が生成されます。

- `news_report_<timestamp>.md` / `.json`: そのときの完全なレポート
- `latest.md`: 最新レポートへの固定パス (Botや他ツールからの参照用)

## 対象チャンネル・パラメータの変更

`config.py` で以下を調整できます。

| 項目 | 説明 |
| --- | --- |
| `CHANNELS` | 対象チャンネルのハンドル一覧 |
| `MAX_VIDEOS_PER_CHANNEL` | チャンネルごとに遡る動画数 |
| `NEWS_LOOKBACK_DAYS` | 動画関連ニュースの検索期間 (日) |
| `MAX_NEWS_PER_VIDEO` | 動画1本あたりの関連ニュース保持数 |
| `MAX_GENERAL_TRENDS` | 一般トレンドニュースの保持件数 |
| `TREND_TOPIC_WEIGHTS` | ニュースカテゴリごとの重み |
| `STOPWORDS` | キーワード抽出から除外する一般語 |

## 定期自動実行 (GitHub Actions)

`.github/workflows/collect_news.yml` で毎日1回 (JST 22:00) 自動実行するワークフローを用意しています。

1. リポジトリの Settings → Secrets and variables → Actions に `YOUTUBE_API_KEY` を登録
2. ワークフローが自動実行され、`output/latest.md` がリポジトリにコミットされます (手動実行は `workflow_dispatch` から可能)

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
│   ├── youtube_collector.py  # YouTube Data API 連携
│   ├── keyword_extractor.py  # タイトル/概要欄からキーワード抽出
│   ├── news_search.py        # Google News RSS 検索
│   ├── trend_collector.py    # 一般トレンドニュース収集・スコアリング
│   ├── relevance.py          # 関連度スコアリング・重複排除
│   └── report.py             # Markdown/JSONレポート生成
├── .github/workflows/collect_news.yml  # 定期自動実行
└── output/                 # 生成レポート (latest.md 以外はgit管理外)
```

## 制限事項・注意

- Google News RSS の仕様変更やアクセス制限により、取得できるニュース件数が変動することがあります。
- キーワード抽出は正規表現ベースの軽量実装のため、複雑な固有名詞や口語表現は取りこぼす場合があります。精度を上げたい場合は `janome` または `sudachipy` の導入を検討してください (`keyword_extractor.py` は `janome` があれば自動的に優先利用します)。
- 実行環境からのアウトバウンドHTTPS通信 (YouTube Data API / news.google.com) が必要です。サンドボックス環境などでネットワークが制限されている場合は動作しません。
