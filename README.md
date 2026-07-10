# BuzzTrend

A [Sometrend](https://some.co.kr)-style social **buzz monitor**. Tracks how often
your keywords are mentioned across **blog, news, community, YouTube, and social**,
stores a daily time series, shows it on a web dashboard, and raises **spike alerts**.

Ships with a **mock data mode** (default) so it runs with zero API keys — every
channel is filled with realistic synthetic history. Flip a switch and add keys to
pull real data.

## Channels

| Channel | Region | Real-data source | Status |
|---|---|---|---|
| Blog | KR | Naver Search API | ✅ |
| News | KR | Naver Search API | ✅ |
| Community (Cafe) | KR | Naver Search API | ✅ |
| YouTube | Global | YouTube Data API v3 | ✅ |
| Community (Reddit) | Global | Reddit OAuth search | ✅ |
| Instagram | Global | — | ⚠️ mock only¹ |
| Facebook | Global | — | ⚠️ mock only¹ |

¹ Meta's official APIs don't allow public keyword search for arbitrary terms.
These channels display in mock mode but return 0 in real mode (no scraping).

## Quick start

```bash
cd buzztrend
python -m venv .venv && .venv\Scripts\activate      # Windows PowerShell
pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:8000 — on first run it seeds ~90 days of demo data for a
handful of default keywords. Add your own from the dashboard.

## Dashboard features (Sometrend-style)

- **출처 선택** — pick any mix of 인스타그램/커뮤니티/뉴스/블로그/페이스북/유튜브/레딧
- **기간** — 1/3/6/12개월 presets or a custom date range (12 months of history)
- **키워드 관리** — add/delete keywords freely from the sidebar
- **포함어** — substring filter; "하츄핑" also matches "하츄핑콘서트" (AND for multiple words)
- **원문 보기** — sample posts per mention; links open the platform's real search results
- **엑셀 다운로드** — daily counts + post sample as raw-data sheets
- **급증 알림** — spike detection vs the trailing 7-day average

## Two front-ends (same backend)

The collectors, database, and services are shared. Pick whichever UI you prefer:

| | Command | URL | Best for |
|---|---|---|---|
| **Streamlit** (recommended for editing) | `python -m streamlit run streamlit_app.py` | http://localhost:8501 | Fast tweaks in pure Python |
| **FastAPI** web app | `python run.py` | http://127.0.0.1:8000 | Public/multi-user, built-in scheduler |

The Streamlit app has a **Collect today's buzz** button, but for unattended
collection run `python cli.py collect` on a timer (Windows Task Scheduler), or
keep `python run.py` running — its scheduler collects every hour.

## How it works

```
collectors/  → services/collection.py → SQLite (buzz_daily)
                                       → services/alerts.py (spike detection)
scheduler.py → runs collection every COLLECT_INTERVAL_MINUTES
api.py       → FastAPI dashboard + JSON API
```

- **Buzz count** = matches for a keyword in a channel on a given day.
- **Spike alert** = today's count ≥ `ALERT_SPIKE_RATIO` × trailing 7-day average.

## CLI (no server)

```bash
python cli.py seed              # regenerate mock history
python cli.py add "삼성전자"
python cli.py collect           # collect today + check alerts
python cli.py list
```

## Switching to real data

1. `copy .env.example .env`
2. Set `USE_MOCK=false` and fill in the keys you have:
   - **Naver** — register an app at https://developers.naver.com (Search API)
   - **YouTube** — enable *YouTube Data API v3* in Google Cloud, create an API key
   - **Reddit** — create a "script" app at https://www.reddit.com/prefs/apps
3. Restart. Only channels with valid keys will return data; others are skipped.

> Note: Naver's API returns an all-time match total, not a per-day figure, so in
> real mode the daily series reflects snapshots taken at collection time. For a
> true daily metric, narrow queries by date or store day-over-day deltas
> (see the comment in `app/collectors/naver.py`).

## Config (.env)

| Var | Default | Meaning |
|---|---|---|
| `USE_MOCK` | `true` | Use synthetic data instead of real APIs |
| `COLLECT_INTERVAL_MINUTES` | `60` | Scheduler cadence |
| `SEED_DAYS` | `90` | Days of history generated on seed |
| `ALERT_SPIKE_RATIO` | `1.5` | Spike threshold vs 7-day average |

## Project layout

```
app/
  config.py            channels, settings, defaults
  models.py            Keyword / BuzzDaily / AlertEvent
  collectors/          one module per source (+ mock generator)
  services/            collection, alerts, analytics, seeding
  scheduler.py         background job
  api.py               FastAPI app + routes
  templates/           dashboard, keyword detail, alerts
run.py                 serve
cli.py                 offline operations
```
