"""News via public RSS search feeds (Google News, Bing News). No API key needed."""
from __future__ import annotations

from urllib.parse import quote_plus

import feedparser

from ..models import Result
from .base import Source


def _iso(entry) -> str | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    return f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}" if t else None


class _RSSNews(Source):
    category = "News"
    url_template = ""

    def feed_url(self, query: str, location) -> str:
        return self.url_template.format(q=quote_plus(query))

    def search(self, query, location, limit):
        feed = feedparser.parse(self.get(self.feed_url(query, location)).content)
        out = []
        for e in feed.entries[:limit]:
            out.append(Result(
                title=e.get("title", ""), url=e.get("link", ""), source=self.name,
                snippet=_strip_html(e.get("summary", "")), published=_iso(e),
                category="News",
            ))
        return out


def _strip_html(s: str) -> str:
    from bs4 import BeautifulSoup
    return BeautifulSoup(s, "html.parser").get_text(" ", strip=True)


class GoogleNews(_RSSNews):
    name = "google_news"

    def feed_url(self, query, location):
        cc = location.country_code if location else "US"
        return (f"https://news.google.com/rss/search?q={quote_plus(query)}"
                f"&hl=en-{cc}&gl={cc}&ceid={cc}:en")


class BingNews(_RSSNews):
    name = "bing_news"
    url_template = "https://www.bing.com/news/search?q={q}&format=rss"
