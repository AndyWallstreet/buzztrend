"""Mention-level data: individual posts behind the daily counts.

In mock mode each (keyword, channel, day) gets a deterministic sample of
synthetic posts (text, author, likes, comments, link). This powers:

- 원문 viewer  — a table of posts, each linking to the platform's real search
  page for that phrase (mock posts aren't real, so linking to a live platform
  search is the honest click-through).
- 포함어 filter — substring match on post text, so "하츄핑" also hits
  compound words like "하츄핑콘서트". Daily counts under a 포함어 filter are
  estimated by scaling the true daily count by the matched share of the sample.
- 엑셀 다운로드 — raw daily counts + the post sample as sheets.
"""
from __future__ import annotations

from datetime import date as date_cls, timedelta
from urllib.parse import quote

from .. import config
from ..collectors.mock import _unit, mock_count

# Real platform search pages — clicking a mock post opens live results for the
# phrase on that platform.
PLATFORM_SEARCH = {
    "naver_blog": "https://search.naver.com/search.naver?ssc=tab.blog.all&query={q}",
    "naver_news": "https://search.naver.com/search.naver?ssc=tab.news.all&query={q}",
    "naver_cafe": "https://search.naver.com/search.naver?ssc=tab.cafe.all&query={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "reddit": "https://www.reddit.com/search/?q={q}",
    "instagram": "https://www.instagram.com/explore/search/keyword/?q={q}",
    "facebook": "https://www.facebook.com/search/posts?q={q}",
}

# Suffixes form compound words ("하츄핑" + "콘서트" → "하츄핑콘서트") so the
# 포함어 substring filter has something meaningful to match against.
SUFFIXES = ["", "", "", "", " 콘서트", "콘서트", " 굿즈", "굿즈", " 이벤트",
            " 후기", "후기", " 리뷰", " 팝업스토어", " 신상", " 인형",
            " 케이크", " 티켓", " 예매", " 나눔", " 언박싱", " 스티커"]

TEMPLATES = [
    "{t} 다녀왔어요! 진짜 최고였어요 💕",
    "오늘 {t} 소식 공유합니다~",
    "{t} 완전 추천해요!!",
    "{t} 관련 정보 정리해봤어요",
    "요즘 {t} 인기 실감하네요 ㅎㅎ",
    "{t} 어떤가요? 구매 고민중이에요",
    "{t} 구매 후기 올려요 📦",
    "드디어 {t} 겟했습니다 🎉",
    "{t} 보러 왔어요, 사람 정말 많네요",
    "{t} 정보 아시는 분 계신가요?",
]

NEWS_TEMPLATES = [
    "{t}, 검색량 급증…업계 주목",
    "'{t}' 관련 시장 성장세 뚜렷",
    "[트렌드] {t} 인기 비결은?",
    "{t} 열풍, 어디까지 가나",
    "\"{t}\" 소비자 관심 집중",
]

# Like/comment scale per channel (rough social-platform feel)
_LIKE_SCALE = {"instagram": 8000, "facebook": 3000, "youtube": 5000,
               "reddit": 2000, "naver_blog": 400, "naver_cafe": 300,
               "naver_news": 150}


def platform_link(channel: str, phrase: str) -> str:
    return PLATFORM_SEARCH[channel].format(q=quote(phrase))


def sample_mentions(term: str, channel: str, day: date_cls, limit: int = 10):
    """Deterministic sample of posts for one (keyword, channel, day).

    Returns (mentions, true_daily_count). The sample is capped at `limit`;
    the true count says how many the sample represents.
    """
    total = mock_count(term, channel, day)
    n = min(total, limit)
    templates = NEWS_TEMPLATES if channel == "naver_news" else TEMPLATES

    out = []
    for i in range(n):
        u = lambda *p: _unit(term, channel, day.isoformat(), i, *p)
        compound = term + SUFFIXES[int(u("sfx") * len(SUFFIXES)) % len(SUFFIXES)]
        text = templates[int(u("tpl") * len(templates)) % len(templates)].format(t=compound)
        likes = int((u("like") ** 2) * _LIKE_SCALE.get(channel, 500))
        comments = int(likes * (0.02 + u("cmt") * 0.15))
        author = ("뉴스" if channel == "naver_news" else "user_") + \
                 format(int(u("auth") * 0xFFFFFF), "06x")
        hh, mm = 8 + int(u("hh") * 15), int(u("mm") * 60)
        out.append({
            "date": day.isoformat(),
            "time": f"{hh:02d}:{mm:02d}",
            "channel": channel,
            "channel_label": config.CHANNELS_BY_KEY[channel]["label"],
            "author": author,
            "text": text,
            "likes": likes,
            "comments": comments,
            "url": platform_link(channel, compound),
        })
    return out, total


def _match(text: str, words: list[str]) -> bool:
    return all(w in text for w in words)


def parse_include(raw: str) -> list[str]:
    """'하츄핑, 콘서트' → ['하츄핑', '콘서트'] (documents must contain ALL)."""
    return [w for w in raw.replace(",", " ").split() if w]


def mentions_range(term: str, channels: list[str], start: date_cls,
                   end: date_cls, include_words: list[str] | None = None,
                   per_day_limit: int = 6):
    """Generate the mention sample + (estimated) daily counts over a range.

    Returns (mentions, daily) where:
      mentions: list of post dicts (filtered by 포함어 if given)
      daily:    list of {date, channel, count} — true counts, or scaled
                estimates when a 포함어 filter is active.
    """
    include_words = include_words or []
    mentions, daily = [], []
    days = (end - start).days + 1
    for off in range(days):
        day = start + timedelta(days=off)
        for ch in channels:
            sample, total = sample_mentions(term, ch, day, per_day_limit)
            if include_words:
                kept = [m for m in sample if _match(m["text"], include_words)]
                # Estimate: true count × matched share of the sample.
                est = round(total * len(kept) / len(sample)) if sample else 0
                mentions.extend(kept)
                daily.append({"date": day, "channel": ch, "count": est})
            else:
                mentions.extend(sample)
                daily.append({"date": day, "channel": ch, "count": total})
    mentions.sort(key=lambda m: (m["date"], m["time"]), reverse=True)
    return mentions, daily
