"""YouTube Data API v3 collector.

Uses search.list's pageInfo.totalResults as a buzz proxy. Note the API caps
totalResults and each search costs 100 quota units against the daily 10k
default, so track a modest number of keywords.
"""
import httpx

from .. import config
from .base import BaseCollector


class YouTubeCollector(BaseCollector):
    channel = "youtube"

    def fetch(self, term: str, day) -> int:
        resp = httpx.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet", "q": term, "type": "video",
                "maxResults": 1, "key": config.YOUTUBE_API_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return int(resp.json().get("pageInfo", {}).get("totalResults", 0))
