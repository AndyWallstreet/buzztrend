"""Reddit collector — the 'global community' channel.

Counts recent submissions matching the term via Reddit's OAuth search. Reddit
search returns a bounded window, so this is an approximate buzz signal rather
than an exhaustive count.
"""
import httpx

from .. import config
from .base import BaseCollector

_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_SEARCH_URL = "https://oauth.reddit.com/search"


class RedditCollector(BaseCollector):
    channel = "reddit"

    def _token(self) -> str:
        resp = httpx.post(
            _TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(config.REDDIT_CLIENT_ID, config.REDDIT_CLIENT_SECRET),
            headers={"User-Agent": config.REDDIT_USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def fetch(self, term: str, day) -> int:
        headers = {
            "Authorization": f"bearer {self._token()}",
            "User-Agent": config.REDDIT_USER_AGENT,
        }
        resp = httpx.get(
            _SEARCH_URL, headers=headers,
            params={"q": term, "limit": 100, "sort": "new", "t": "week"},
            timeout=10,
        )
        resp.raise_for_status()
        return len(resp.json().get("data", {}).get("children", []))
