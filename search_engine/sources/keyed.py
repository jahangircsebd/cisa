"""Optional higher-quality backends that need an API key (set via env vars)."""
from __future__ import annotations

from ..models import Result
from .base import Source


class YouTubeAPI(Source):
    name = "youtube_api"
    category = "Social"
    env_key = "YOUTUBE_API_KEY"

    def search(self, query, location, limit):
        params = {"part": "snippet", "q": query, "type": "video", "maxResults": min(limit, 50),
                  "key": self.api_key, "regionCode": location.country_code if location else "US"}
        data = self.get("https://www.googleapis.com/youtube/v3/search", params=params).json()
        out = []
        for item in data.get("items", []):
            sn, vid = item["snippet"], item["id"].get("videoId")
            out.append(Result(
                title=sn.get("title", ""), url=f"https://www.youtube.com/watch?v={vid}",
                source=self.name, snippet=sn.get("description", ""),
                published=(sn.get("publishedAt") or "")[:10] or None, platform="YouTube",
            ))
        return out


class SerpAPI(Source):
    """Google web results via serpapi.com, with native location targeting."""
    name = "serpapi"
    env_key = "SERPAPI_KEY"

    def search(self, query, location, limit):
        params = {"engine": "google", "q": query, "num": min(limit, 100), "api_key": self.api_key}
        if location:
            params["location"] = f"{location.name}, United States" if location.country_code == "US" \
                else location.name
        data = self.get("https://serpapi.com/search.json", params=params).json()
        return [Result(title=r.get("title", ""), url=r.get("link", ""), source=self.name,
                       snippet=r.get("snippet", ""), published=r.get("date"))
                for r in data.get("organic_results", [])[:limit]]


class GoogleCSE(Source):
    """Google Programmable Search Engine (needs GOOGLE_CSE_KEY and GOOGLE_CSE_ID)."""
    name = "google_cse"
    env_key = "GOOGLE_CSE_KEY"

    def available(self):
        import os
        return bool(self.api_key and os.environ.get("GOOGLE_CSE_ID"))

    def search(self, query, location, limit):
        import os
        out = []
        for start in range(1, min(limit, 100) + 1, 10):
            data = self.get("https://www.googleapis.com/customsearch/v1", params={
                "key": self.api_key, "cx": os.environ["GOOGLE_CSE_ID"], "q": query,
                "start": start, "gl": "us"}).json()
            items = data.get("items", [])
            out += [Result(title=i.get("title", ""), url=i.get("link", ""), source=self.name,
                           snippet=i.get("snippet", "")) for i in items]
            if len(items) < 10:
                break
        return out[:limit]
