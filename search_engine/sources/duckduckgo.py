"""General web + social media search via DuckDuckGo's HTML endpoint (no key).

Social platforms (TikTok, Instagram, ...) have no open search API, so we use
`site:` queries against a web index to discover public posts/profiles.
"""
from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from ..models import Result
from .base import Source, throttle

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
    pages = 3          # result pages to read (DDG returns ~10-30 per page)
    min_interval = 1.5  # DDG blocks bursts of requests

    def search(self, query, location, limit):
        q = f"{query} site:{self.site}" if self.site else query
        return self.search_pages(q, limit)

    def search_pages(self, q: str, limit: int) -> list[Result]:
        out: list[Result] = []
        seen: set[str] = set()
        for page in range(self.pages):
            data = {"q": q, "kl": "us-en"}
            if page:
                data.update({"s": str(len(out)), "dc": str(len(out) + 1), "nextParams": "",
                             "v": "l", "o": "json", "api": "d.js"})
            try:
                throttle(self.endpoint, self.min_interval)
                resp = self.session.post(self.endpoint, data=data, timeout=self.timeout)
                resp.raise_for_status()
            except Exception:
                if not page:
                    raise
                break  # keep what earlier pages returned
            new = [r for r in parse_ddg_html(resp.text, self.name, limit) if r.url not in seen]
            if not new:
                break
            seen.update(r.url for r in new)
            out += new
            if len(out) >= limit:
                break
        return out[:limit]


def make_social_source(key: str) -> type[DuckDuckGoWeb]:
    return type(f"DDG_{key}", (DuckDuckGoWeb,), {"name": key, "site": SOCIAL_SITES[key],
                                                   "category": "Social", "pages": 1})
