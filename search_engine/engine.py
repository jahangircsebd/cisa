"""Runs all sources concurrently, then dedupes, scores, geo-tags and ranks results."""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .location import LocationProfile, get_profile
from .models import Result
from .sources import DEFAULT_SOURCES, REGISTRY

log = logging.getLogger(__name__)

STOPWORDS = {"the", "a", "an", "of", "and", "or", "in", "on", "for", "to"}
TRACKING_PARAMS = re.compile(r"^(utm_|fbclid|gclid|ref$|ref_src|igshid|si$)")


def keyword_tokens(keyword: str) -> list[str]:
    return [t for t in re.findall(r"[\w&'-]+", keyword.lower()) if t not in STOPWORDS]


def keyword_score(keyword: str, text: str) -> float:
    """Share of keyword terms present in text, with a bonus for the exact phrase."""
    toks = keyword_tokens(keyword)
    if not toks:
        return 0.0
    low = text.lower()
    found = sum(1 for t in toks if re.search(r"\b" + re.escape(t) + r"\b", low))
    score = found / len(toks)
    phrase = " ".join(toks)
    if phrase in re.sub(r"\s+", " ", low):
        score = min(1.0, score + 0.2)
    return round(score, 3)


def normalize_url(url: str) -> str:
    p = urlparse(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if not TRACKING_PARAMS.match(k)]
    host = (p.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    return urlunparse(("https", host, p.path.rstrip("/"), "", urlencode(q), ""))


@dataclass
class SearchRun:
    keyword: str
    location: str | None
    started: str
    results: list[Result] = field(default_factory=list)
    source_status: dict[str, str] = field(default_factory=dict)
    queries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"keyword": self.keyword, "location": self.location, "started": self.started,
                "queries": self.queries, "source_status": self.source_status,
                "results": [r.to_dict() for r in self.results]}

    @classmethod
    def from_dict(cls, d: dict) -> "SearchRun":
        run = cls(keyword=d["keyword"], location=d.get("location"),
                  started=d.get("started") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  source_status=d.get("source_status", {}), queries=d.get("queries", []))
        run.results = [Result.from_dict(r) for r in d.get("results", [])]
        return run


def build_queries(keyword: str, location: LocationProfile | None) -> list[str]:
    """Location-qualified query first, plus the bare keyword to catch items that
    mention a city (e.g. Corpus Christi) without naming the state."""
    if not location:
        return [keyword]
    return [f"{keyword} {location.query_term}", keyword]


def score_results(results: list[Result], keyword: str,
                  location: LocationProfile | None) -> list[Result]:
    for r in results:
        text = f"{r.title} {r.snippet} {r.url}"
        r.keyword_score = keyword_score(keyword, text)
        if location:
            r.location_score, r.location_hits = location.score(text, r.domain)
    return results


def dedupe(results: list[Result]) -> list[Result]:
    best: dict[str, Result] = {}
    for r in results:
        if not r.url:
            continue
        key = normalize_url(r.url)
        cur = best.get(key)
        if cur is None:
            best[key] = r
        else:
            if r.source not in cur.source.split(", "):
                cur.source += f", {r.source}"
            if len(r.snippet) > len(cur.snippet):
                cur.snippet = r.snippet
            cur.published = cur.published or r.published
    return list(best.values())


class SearchEngine:
    def __init__(self, sources: list[str] | None = None, limit_per_source: int = 30,
                 workers: int = 8, timeout: float = 20):
        names = sources or DEFAULT_SOURCES
        unknown = [n for n in names if n not in REGISTRY]
        if unknown:
            raise ValueError(f"Unknown source(s): {unknown}. Available: {sorted(REGISTRY)}")
        self.sources = [REGISTRY[n](timeout=timeout) for n in names]
        self.limit = limit_per_source
        self.workers = workers

    def search(self, keyword: str, location: str | None = None,
               min_keyword_score: float = 0.5, location_only: bool = False) -> SearchRun:
        profile = get_profile(location)
        run = SearchRun(keyword=keyword, location=profile.name if profile else None,
                        started=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        queries=build_queries(keyword, profile))
        raw: list[Result] = []
        jobs = {}
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for src in self.sources:
                if not src.available():
                    run.source_status[src.name] = f"skipped (set {src.env_key})"
                    continue
                for q in run.queries:
                    jobs[pool.submit(src.search, q, profile, self.limit)] = src.name
            counts: dict[str, int] = {}
            for fut in as_completed(jobs):
                name = jobs[fut]
                try:
                    found = fut.result()
                    raw.extend(found)
                    counts[name] = counts.get(name, 0) + len(found)
                    run.source_status.setdefault(name, "ok")
                except Exception as exc:  # one broken source must not kill the run
                    log.info("source %s failed: %s", name, exc)
                    run.source_status[name] = f"error: {type(exc).__name__}: {exc}"[:200]
            for name, n in counts.items():
                if run.source_status.get(name) == "ok":
                    run.source_status[name] = f"ok ({n} raw results)"

        run.results = rank(raw, keyword, profile, min_keyword_score, location_only)
        return run


def rank(results: list[Result], keyword: str, profile: LocationProfile | None,
         min_keyword_score: float = 0.5, location_only: bool = False) -> list[Result]:
    results = score_results(dedupe(results), keyword, profile)
    results = [r for r in results if r.keyword_score >= min_keyword_score]
    if location_only and profile:
        results = [r for r in results if r.location_score > 0]
    results.sort(key=lambda r: (r.relevance, r.published or ""), reverse=True)
    return results
