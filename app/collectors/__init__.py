"""Collector factory.

Each collector exposes:  channel: str  and  fetch(term, day) -> int

In mock mode every channel is served by a deterministic generator so the app
runs with zero credentials. Flip USE_MOCK=false (and provide keys) to use the
real API-backed collectors.
"""
from .. import config
from .mock import MockCollector


def get_collectors():
    if config.USE_MOCK:
        return [MockCollector(c["key"]) for c in config.CHANNELS]

    # Real collectors — imported lazily so mock mode needs no network stack.
    # Only channels whose credentials are configured are included; the rest
    # are skipped silently. Facebook/Instagram have no public keyword API.
    from .naver import NaverCollector
    from .youtube import YouTubeCollector
    from .reddit import RedditCollector

    cols = []
    if config.NAVER_CLIENT_ID and config.NAVER_CLIENT_SECRET:
        cols += [NaverCollector("naver_blog"), NaverCollector("naver_news"),
                 NaverCollector("naver_cafe")]
    if config.YOUTUBE_API_KEY:
        cols.append(YouTubeCollector())
    if config.REDDIT_CLIENT_ID and config.REDDIT_CLIENT_SECRET:
        cols.append(RedditCollector())
    return cols


def mock_collectors():
    """Always-mock collectors (used for seeding history regardless of mode)."""
    return [MockCollector(c["key"]) for c in config.CHANNELS]
