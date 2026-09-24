from .academic import Crossref, OpenAlex, SemanticScholar
from .base import Source
from .duckduckgo import SOCIAL_SITES, DuckDuckGoWeb, make_social_source
from .gdelt import Gdelt
from .keyed import GoogleCSE, SerpAPI, YouTubeAPI
from .local import LocalNews, LocalWeb
from .misc import Bluesky, Podcasts, Wikipedia
from .reddit import Reddit
from .rss_news import BingNews, GoogleNews

REGISTRY: dict[str, type[Source]] = {
    "google_news": GoogleNews,
    "bing_news": BingNews,
    "gdelt": Gdelt,
    "local_news": LocalNews,
    "local_web": LocalWeb,
    "web": DuckDuckGoWeb,
    "reddit_api": Reddit,
    "bluesky": Bluesky,
    "podcasts": Podcasts,
    "wikipedia": Wikipedia,
    "openalex": OpenAlex,
    "crossref": Crossref,
    "semantic_scholar": SemanticScholar,
    "youtube_api": YouTubeAPI,
    "serpapi": SerpAPI,
    "google_cse": GoogleCSE,
    **{key: make_social_source(key) for key in SOCIAL_SITES},
}

DEFAULT_SOURCES = ["google_news", "bing_news", "gdelt", "local_news", "local_web", "web",
                   "tiktok", "youtube", "instagram", "facebook", "x", "linkedin",
                   "reddit_api", "bluesky", "podcasts", "wikipedia",
                   "openalex", "crossref", "semantic_scholar",
                   "youtube_api", "serpapi", "google_cse"]

__all__ = ["REGISTRY", "DEFAULT_SOURCES", "Source"]
