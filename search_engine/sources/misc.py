"""Other free sources: Wikipedia, podcasts (Apple/iTunes), Bluesky."""
from __future__ import annotations

import os
import re

from ..models import Result
from .base import Source


class Wikipedia(Source):
    name = "wikipedia"
    uses_location_query = False

    def search(self, query, location, limit):
        data = self.get("https://en.wikipedia.org/w/api.php", params={
            "action": "query", "list": "search", "srsearch": query, "format": "json",
            "srlimit": min(limit, 50)}).json()
        out = []
        for hit in data.get("query", {}).get("search", []):
            title = hit["title"]
            out.append(Result(
                title=f"{title} – Wikipedia",
                url="https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
                source=self.name, snippet=re.sub(r"<[^>]+>", "", hit.get("snippet", "")),
                published=(hit.get("timestamp") or "")[:10] or None, category="Web"))
        return out


class Podcasts(Source):
    """Podcast episodes via the free iTunes Search API."""
    name = "podcasts"
    category = "Media"
    uses_location_query = False

    def search(self, query, location, limit):
        data = self.get("https://itunes.apple.com/search", params={
            "term": query.replace('"', ""), "media": "podcast", "entity": "podcastEpisode",
            "limit": min(limit, 200), "country": location.country_code if location else "US"}).json()
        return [Result(
            title=f"{e.get('trackName', '')} ({e.get('collectionName', '')})",
            url=e.get("trackViewUrl") or e.get("episodeUrl") or "", source=self.name,
            snippet=(e.get("description") or e.get("shortDescription") or "")[:500],
            published=(e.get("releaseDate") or "")[:10] or None, category="Media",
            platform="Podcast") for e in data.get("results", [])]


class Bluesky(Source):
    """Bluesky posts. Works without login where the public API allows it; set
    BLUESKY_HANDLE and BLUESKY_APP_PASSWORD (an app password) for reliable access."""
    name = "bluesky"
    category = "Social"

    def _auth_headers(self) -> tuple[str, dict]:
        handle, pw = os.environ.get("BLUESKY_HANDLE"), os.environ.get("BLUESKY_APP_PASSWORD")
        if not (handle and pw):
            return "https://public.api.bsky.app", {}
        if not getattr(self, "_token", None):
            resp = self.session.post("https://bsky.social/xrpc/com.atproto.server.createSession",
                                     json={"identifier": handle, "password": pw}, timeout=self.timeout)
            resp.raise_for_status()
            self._token = resp.json()["accessJwt"]
        return "https://bsky.social", {"Authorization": f"Bearer {self._token}"}

    def search(self, query, location, limit):
        host, headers = self._auth_headers()
        data = self.get(f"{host}/xrpc/app.bsky.feed.searchPosts",
                        params={"q": query, "limit": min(limit, 100)}, headers=headers).json()
        out = []
        for p in data.get("posts", []):
            handle = p.get("author", {}).get("handle", "")
            rkey = p.get("uri", "").rsplit("/", 1)[-1]
            text = p.get("record", {}).get("text", "")
            out.append(Result(title=f"@{handle}: {text[:90]}", snippet=text,
                              url=f"https://bsky.app/profile/{handle}/post/{rkey}",
                              source=self.name, platform="Bluesky",
                              published=(p.get("indexedAt") or "")[:10] or None))
        return out
