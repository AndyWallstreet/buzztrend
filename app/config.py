"""Central configuration. Reads .env; sensible mock-mode defaults."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# --- storage ---
DB_PATH = os.getenv("BUZZTREND_DB", str(BASE_DIR / "buzztrend.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# --- mode ---
USE_MOCK = _bool("USE_MOCK", True)

# --- scheduling / behaviour ---
COLLECT_INTERVAL_MINUTES = int(os.getenv("COLLECT_INTERVAL_MINUTES", "60"))
SEED_DAYS = int(os.getenv("SEED_DAYS", "90"))
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
    {"key": "naver_blog", "label": "Blog", "region": "kr", "color": "#22c55e"},
    {"key": "naver_news", "label": "News", "region": "kr", "color": "#3b82f6"},
    {"key": "naver_cafe", "label": "Community (Cafe)", "region": "kr", "color": "#f97316"},
    {"key": "youtube", "label": "YouTube", "region": "global", "color": "#ef4444"},
    {"key": "reddit", "label": "Community (Reddit)", "region": "global", "color": "#a855f7"},
    {"key": "instagram", "label": "Instagram", "region": "global", "color": "#ec4899"},
    {"key": "facebook", "label": "Facebook", "region": "global", "color": "#0ea5e9"},
]
CHANNEL_KEYS = [c["key"] for c in CHANNELS]
CHANNELS_BY_KEY = {c["key"]: c for c in CHANNELS}

# Default keywords seeded on first run (mix of KR + global)
DEFAULT_KEYWORDS = ["아이폰", "삼성전자", "테슬라", "Tesla", "ChatGPT"]
