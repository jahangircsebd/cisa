from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional
from urllib.parse import urlparse

import requests

from ..models import Result

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


# Shared across all sources/threads: the next time each host may be called.
_host_lock = threading.Lock()
_host_next: dict[str, float] = {}


def throttle(url: str, interval: float) -> None:
    """Space out requests to one host so free endpoints don't block us."""
    if interval <= 0:
        return
    host = urlparse(url).hostname or ""
    with _host_lock:
        now = time.monotonic()
        start = max(now, _host_next.get(host, 0.0))
        _host_next[host] = start + interval
    if start > now:
        time.sleep(start - now)


class Source:
    """A search backend. Subclasses implement `search`."""

    name = "base"
    category = "Web"
    env_key: Optional[str] = None  # API key env var; source is skipped if unset
    # per_query sources get every query string; others implement
    # search_subject() and are called once with the whole Subject.
    per_query = True
    uses_location_query = True     # False: skip "<keyword> Texas" style queries
    min_interval = 0.0             # seconds between requests to the same host

    def __init__(self, session: Optional[requests.Session] = None, timeout: float = 20):
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.timeout = timeout

    @property
    def api_key(self) -> Optional[str]:
        return os.environ.get(self.env_key) if self.env_key else None

    def available(self) -> bool:
        return self.env_key is None or bool(self.api_key)

    def get(self, url: str, **kwargs) -> requests.Response:
        throttle(url, self.min_interval)
        resp = self.session.get(url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp

    def search(self, query: str, location, limit: int) -> list[Result]:
        raise NotImplementedError

    def search_subject(self, subject, location, limit: int) -> list[Result]:
        raise NotImplementedError
