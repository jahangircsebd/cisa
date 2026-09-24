"""GDELT 2.0 DOC API: global news index, free, no key."""
from __future__ import annotations

from ..models import Result
from .base import Source


class Gdelt(Source):
    name = "gdelt"
    category = "News"
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"

    def search(self, query, location, limit):
        q = query
        if location and location.country_code:
            q += f" sourcecountry:{location.country_code}"
        params = {"query": q, "mode": "artlist", "format": "json",
                  "maxrecords": min(limit, 250), "sort": "datedesc"}
        data = self.get(self.endpoint, params=params).json()
        out = []
        for a in data.get("articles", [])[:limit]:
            seen = a.get("seendate", "")
            out.append(Result(
                title=a.get("title", ""), url=a.get("url", ""), source=self.name,
                snippet=a.get("domain", ""), category="News",
                published=f"{seen[:4]}-{seen[4:6]}-{seen[6:8]}" if len(seen) >= 8 else None,
            ))
        return out
