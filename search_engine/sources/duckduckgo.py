"""General web + social media search via DuckDuckGo's HTML endpoint (no key).

Social platforms (TikTok, Instagram, ...) have no open search API, so we use
`site:` queries against a web index to discover public posts/profiles.
"""
from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from ..models import Result
from .base import Source

SOCIAL_SITES = {
    "tiktok": "tiktok.com",
    "youtube": "youtube.com",
    "instagram": "instagram.com",
    "facebook": "facebook.com",
    "x": "x.com",
    "linkedin": "linkedin.com",
    "reddit": "reddit.com",
}


def _clean_link(href: str) -> str:
    # DDG wraps results as //duckduckgo.com/l/?uddg=<encoded url>
    if "uddg=" in href:
        return unquote(parse_qs(urlparse(href).query)["uddg"][0])
    return href


def parse_ddg_html(html: str, source: str, limit: int) -> list[Result]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for block in soup.select("div.result"):
        a = block.select_one("a.result__a")
        if not a or not a.get("href"):
            continue
        snip = block.select_one(".result__snippet")
        out.append(Result(
            title=a.get_text(" ", strip=True), url=_clean_link(a["href"]), source=source,
            snippet=snip.get_text(" ", strip=True) if snip else "",
        ))
        if len(out) >= limit:
            break
    return out


class DuckDuckGoWeb(Source):
    name = "web"
    endpoint = "https://html.duckduckgo.com/html/"
    site: str | None = None

    def search(self, query, location, limit):
        q = f"{query} site:{self.site}" if self.site else query
        html = self.session.post(self.endpoint, data={"q": q, "kl": "us-en"},
                                 timeout=self.timeout)
        html.raise_for_status()
        return parse_ddg_html(html.text, self.name, limit)


def make_social_source(key: str) -> type[DuckDuckGoWeb]:
    return type(f"DDG_{key}", (DuckDuckGoWeb,), {"name": key, "site": SOCIAL_SITES[key],
                                                   "category": "Social"})
