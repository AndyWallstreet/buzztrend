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
    from .naver import NaverCollector
    from .youtube import YouTubeCollector
    from .reddit import RedditCollector
    from .social import UnsupportedCollector

    return [
        NaverCollector("naver_blog"),
        NaverCollector("naver_news"),
        NaverCollector("naver_cafe"),
        YouTubeCollector(),
        RedditCollector(),
        # Facebook/Instagram public keyword search is not available via their
        # official APIs; kept as explicit no-data channels so the UI is honest.
        UnsupportedCollector("instagram"),
        UnsupportedCollector("facebook"),
    ]


def mock_collectors():
    """Always-mock collectors (used for seeding history regardless of mode)."""
    return [MockCollector(c["key"]) for c in config.CHANNELS]
