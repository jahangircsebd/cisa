from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional
from urllib.parse import urlparse

# Maps a domain to a human-friendly media category.
PLATFORM_BY_DOMAIN = {
    "tiktok.com": "TikTok",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "instagram.com": "Instagram",
    "facebook.com": "Facebook",
    "x.com": "X / Twitter",
    "twitter.com": "X / Twitter",
    "reddit.com": "Reddit",
    "linkedin.com": "LinkedIn",
    "threads.net": "Threads",
    "bsky.app": "Bluesky",
}
SOCIAL_PLATFORMS = set(PLATFORM_BY_DOMAIN.values())


def domain_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def platform_of(url: str) -> Optional[str]:
    host = domain_of(url)
    for dom, name in PLATFORM_BY_DOMAIN.items():
        if host == dom or host.endswith("." + dom):
            return name
    return None


@dataclass
class Result:
    title: str
    url: str
    source: str                      # which search backend found it
    snippet: str = ""
    published: Optional[str] = None  # ISO date string if known
    category: str = "Web"            # News / Social / Web / Academic
    platform: Optional[str] = None   # TikTok, YouTube, ... for social
    keyword_score: float = 0.0
    location_score: float = 0.0
    location_hits: list[str] = field(default_factory=list)
    # Filled by page enrichment (enrich.py): text around keyword/location
    # matches on the actual page, whether the name was found there, and status.
    page_excerpt: str = ""
    name_on_page: Optional[bool] = None
    page_status: Optional[str] = None

    def __post_init__(self) -> None:
        if self.platform is None:
            self.platform = platform_of(self.url)
        if self.platform in SOCIAL_PLATFORMS:
            self.category = "Social"
        elif self.category == "Web" and domain_of(self.url).endswith(".edu"):
            self.category = "Academic"

    @property
    def domain(self) -> str:
        return domain_of(self.url)

    @property
    def relevance(self) -> float:
        return round(0.6 * self.keyword_score + 0.4 * self.location_score, 3)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domain"] = self.domain
        d["relevance"] = self.relevance
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Result":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in fields})
