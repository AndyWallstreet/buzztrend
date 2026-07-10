"""Naver Search API collectors (blog / news / cafe).

Note: Naver's `total` is an all-time match count, not a per-day figure. For a
production buzz metric you'd narrow by date or store daily deltas; here we take
the snapshot as "today's" value, which is fine for trend tracking.
"""
import httpx

from .. import config
from .base import BaseCollector

_ENDPOINTS = {
    "naver_blog": "https://openapi.naver.com/v1/search/blog.json",
    "naver_news": "https://openapi.naver.com/v1/search/news.json",
    "naver_cafe": "https://openapi.naver.com/v1/search/cafearticle.json",
}


class NaverCollector(BaseCollector):
    def __init__(self, channel: str):
        self.channel = channel
        self.url = _ENDPOINTS[channel]

    def fetch(self, term: str, day) -> int:
        headers = {
            "X-Naver-Client-Id": config.NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
        }
        resp = httpx.get(self.url, headers=headers,
                        params={"query": term, "display": 1}, timeout=10)
        resp.raise_for_status()
        return int(resp.json().get("total", 0))
