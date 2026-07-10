"""Deterministic mock buzz generator.

Produces realistic-looking daily counts: a per-keyword/channel baseline, a slow
multi-week trend, weekly seasonality, day-to-day noise, and occasional spikes.
Deterministic (hash-seeded) so charts are stable across restarts and history can
be regenerated identically.
"""
import hashlib
import math
from datetime import date as date_cls

from .base import BaseCollector


def _unit(*parts) -> float:
    """Stable pseudo-random float in [0, 1) from the given parts."""
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:8], 16) / 0xFFFFFFFF


def mock_count(term: str, channel: str, day: date_cls) -> int:
    # Per-channel scale — video/community channels are chattier than news.
    channel_scale = {
        "naver_blog": 1.0, "naver_news": 0.5, "naver_cafe": 0.8,
        "youtube": 0.7, "reddit": 0.6, "instagram": 1.2, "facebook": 0.9,
    }.get(channel, 1.0)

    base = (40 + _unit(term, channel, "base") * 600) * channel_scale
    n = day.toordinal()

    trend = math.sin(n / 45.0 + _unit(term, channel, "phase") * 6.283) * 0.45
    weekly = math.sin((n % 7) / 7.0 * 6.283) * 0.15
    noise = (_unit(term, channel, day.isoformat()) - 0.5) * 0.5
    mult = max(0.05, 1.0 + trend + weekly + noise)

    count = base * mult
    if _unit(term, channel, day.isoformat(), "spike") > 0.965:  # ~3.5% of days
        count *= 2.0 + _unit(term, channel, day.isoformat(), "mag") * 4.0

    return int(round(count))


class MockCollector(BaseCollector):
    def __init__(self, channel: str):
        self.channel = channel

    def fetch(self, term: str, day: date_cls) -> int:
        return mock_count(term, self.channel, day)
