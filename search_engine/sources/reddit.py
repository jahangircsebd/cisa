from __future__ import annotations

from datetime import datetime, timezone

from ..models import Result
from .base import Source


class Reddit(Source):
    name = "reddit_api"
    category = "Social"

    def search(self, query, location, limit):
        data = self.get("https://www.reddit.com/search.json",
                        params={"q": query, "limit": min(limit, 100), "sort": "relevance"}).json()
        out = []
        for child in data.get("data", {}).get("children", []):
            p = child.get("data", {})
            ts = p.get("created_utc")
            out.append(Result(
                title=p.get("title", ""), url="https://www.reddit.com" + p.get("permalink", ""),
                source=self.name, snippet=(p.get("selftext") or "")[:400],
                published=datetime.fromtimestamp(ts, timezone.utc).date().isoformat() if ts else None,
                platform="Reddit",
            ))
        return out
