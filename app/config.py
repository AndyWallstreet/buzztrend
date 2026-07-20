"""Central configuration. Reads .env; sensible mock-mode defaults."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# --- mode & storage ---
# Real collected data lives in data/buzztrend.db (committed to the repo by the
# nightly GitHub Action). If that file exists, the app automatically switches
# to real mode. An explicit USE_MOCK env var always wins.
_REAL_DB = BASE_DIR / "data" / "buzztrend.db"
if os.getenv("USE_MOCK") is not None:
    USE_MOCK = _bool("USE_MOCK", True)
else:
    USE_MOCK = not _REAL_DB.exists()

_default_db = _REAL_DB if not USE_MOCK and _REAL_DB.exists() else BASE_DIR / "buzztrend.db"
DB_PATH = os.getenv("BUZZTREND_DB", str(_default_db))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Real mode: keywords are managed in this committed file (cloud storage is
# ephemeral, so the repo is the source of truth).
KEYWORDS_FILE = BASE_DIR / "data" / "keywords.txt"

# --- scheduling / behaviour ---
COLLECT_INTERVAL_MINUTES = int(os.getenv("COLLECT_INTERVAL_MINUTES", "60"))
SEED_DAYS = int(os.getenv("SEED_DAYS", "365"))  # 12 months of history
ALERT_SPIKE_RATIO = float(os.getenv("ALERT_SPIKE_RATIO", "1.5"))

# --- API credentials (only used when USE_MOCK is false) ---
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "buzztrend/0.1")

# --- channels ---
# region: kr | global   group: logical channel type shown in the UI
CHANNELS = [
    {"key": "naver_blog", "label": "블로그", "region": "kr", "color": "#22c55e"},
    {"key": "naver_news", "label": "뉴스", "region": "kr", "color": "#f59e0b"},
    {"key": "naver_cafe", "label": "커뮤니티(카페)", "region": "kr", "color": "#f97316"},
    {"key": "youtube", "label": "유튜브", "region": "global", "color": "#ef4444"},
    {"key": "reddit", "label": "커뮤니티(레딧)", "region": "global", "color": "#a855f7"},
    {"key": "instagram", "label": "인스타그램", "region": "global", "color": "#ec4899"},
    {"key": "facebook", "label": "페이스북", "region": "global", "color": "#0ea5e9"},
]

# Channels selected by default in the dashboard (Sometrend-style source picker)
if USE_MOCK:
    DEFAULT_SELECTED_CHANNELS = [
        "instagram", "naver_cafe", "naver_news", "naver_blog", "facebook",
    ]
else:  # real mode: only channels that can actually deliver data
    DEFAULT_SELECTED_CHANNELS = [
        "naver_blog", "naver_news", "naver_cafe", "youtube", "reddit",
    ]
CHANNEL_KEYS = [c["key"] for c in CHANNELS]
CHANNELS_BY_KEY = {c["key"]: c for c in CHANNELS}

# Default keywords seeded on first run (deletable in the UI)
DEFAULT_KEYWORDS = ["고래보석의전설", "하츄핑", "아이폰"]
