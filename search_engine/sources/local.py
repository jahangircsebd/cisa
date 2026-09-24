"""Search only inside a location's own news outlets and institutions.

Uses `site:` restrictions on Google News and DuckDuckGo, in batches so the
query stays a reasonable length. Only runs when a location profile lists domains.
"""
from __future__ import annotations

from .duckduckgo import DuckDuckGoWeb
from .rss_news import GoogleNews

BATCH = 8


def _batches(domains: list[str]):
    for i in range(0, len(domains), BATCH):
        yield domains[i:i + BATCH]


def _site_clause(domains: list[str]) -> str:
    return "(" + " OR ".join(f"site:{d}" for d in domains) + ")"


class LocalNews(GoogleNews):
    """Google News restricted to the location's local outlets (e.g. Texas newspapers/TV)."""
    name = "local_news"
    uses_location_query = False  # the sites already are the location

    def search(self, query, location, limit):
        if not location or not location.news_domains:
            return []
        out = []
        for batch in _batches(location.news_domains):
            for r in super().search(f"{query} {_site_clause(batch)}", location, limit):
                r.source = self.name
                out.append(r)
        return out


class LocalWeb(DuckDuckGoWeb):
    """Web search restricted to local institutions (universities, city/state government)."""
    name = "local_web"
    uses_location_query = False
    pages = 1

    def search(self, query, location, limit):
        if not location or not location.institution_domains:
            return []
        out = []
        for batch in _batches(location.institution_domains):
            out += self.search_pages(f"{query} {_site_clause(batch)}", limit)
        return out
