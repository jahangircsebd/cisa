from __future__ import annotations

import logging
import os
from typing import Optional

import requests

from ..models import Result

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class Source:
    """A search backend. Subclasses implement `search`."""

    name = "base"
    category = "Web"
    env_key: Optional[str] = None  # API key env var; source is skipped if unset

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
        resp = self.session.get(url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp

    def search(self, query: str, location, limit: int) -> list[Result]:
        raise NotImplementedError
