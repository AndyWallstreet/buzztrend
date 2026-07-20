"""YouTube Data API v3 collector.

Filters search by publish date (KST) so the count is a true per-day figure.
Each search costs 100 quota units against the daily 10k default, so track a
modest number of keywords.
"""
from datetime import timedelta

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
                "publishedAfter": f"{day.isoformat()}T00:00:00+09:00",
                "publishedBefore": f"{(day + timedelta(days=1)).isoformat()}T00:00:00+09:00",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return int(resp.json().get("pageInfo", {}).get("totalResults", 0))
