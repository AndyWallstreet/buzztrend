"""Instagram / Facebook.

Meta's official APIs do not expose public keyword/hashtag buzz search for
arbitrary terms (Instagram Graph is limited to your own connected business
accounts; Facebook removed public post search). Rather than scrape — which is
brittle and against ToS — these channels report 0 in real mode. They remain
fully populated in mock mode so you can see how the UI would present them.
"""
from .base import BaseCollector


class UnsupportedCollector(BaseCollector):
    def __init__(self, channel: str):
        self.channel = channel

    def fetch(self, term: str, day) -> int:
        return 0
