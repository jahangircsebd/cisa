"""Runs all sources concurrently, then dedupes, enriches, scores, geo-tags and ranks results."""
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
from .subject import Subject

log = logging.getLogger(__name__)

TRACKING_PARAMS = re.compile(r"^(utm_|fbclid|gclid|ref$|ref_src|igshid|si$)")


def keyword_score(keyword: str, text: str, aliases: list[str] | None = None) -> float:
    return Subject(keyword, aliases or []).score(text)


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
    aliases: list[str] = field(default_factory=list)
    results: list[Result] = field(default_factory=list)
    source_status: dict[str, str] = field(default_factory=dict)
    queries: list[str] = field(default_factory=list)

    @property
    def subject(self) -> Subject:
        return Subject(self.keyword, self.aliases)

    def to_dict(self) -> dict:
        return {"keyword": self.keyword, "aliases": self.aliases, "location": self.location,
                "started": self.started, "queries": self.queries,
                "source_status": self.source_status,
                "results": [r.to_dict() for r in self.results]}

    @classmethod
    def from_dict(cls, d: dict) -> "SearchRun":
        run = cls(keyword=d["keyword"], location=d.get("location"), aliases=d.get("aliases", []),
                  started=d.get("started") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  source_status=d.get("source_status", {}), queries=d.get("queries", []))
        run.results = [Result.from_dict(r) for r in d.get("results", [])]
        return run


def build_queries(keyword: str, location: LocationProfile | None,
                  aliases: list[str] | None = None) -> list[str]:
    return [q for q, _ in Subject(keyword, aliases or []).queries(
        location.query_term if location else None)]


def result_text(r: Result) -> str:
    return f"{r.title} {r.snippet} {r.url} {r.page_excerpt}"


def score_results(results: list[Result], subject: Subject | str,
                  location: LocationProfile | None) -> list[Result]:
    if isinstance(subject, str):
        subject = Subject(subject)
    for r in results:
        text = result_text(r)
        r.keyword_score = subject.score(text)
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
                 workers: int = 8, timeout: float = 20, fetch_pages: int = 60):
        names = sources or DEFAULT_SOURCES
        unknown = [n for n in names if n not in REGISTRY]
        if unknown:
            raise ValueError(f"Unknown source(s): {unknown}. Available: {sorted(REGISTRY)}")
        self.sources = [REGISTRY[n](timeout=timeout) for n in names]
        self.limit = limit_per_source
        self.workers = workers
        self.timeout = timeout
        self.fetch_pages = fetch_pages

    def search(self, keyword: str, location: str | None = None,
               min_keyword_score: float = 0.5, location_only: bool = False,
               aliases: list[str] | None = None, drop_unconfirmed: bool = True) -> SearchRun:
        profile = get_profile(location)
        subject = Subject(keyword, aliases or [])
        queries = subject.queries(profile.query_term if profile else None)
        run = SearchRun(keyword=keyword, aliases=subject.aliases,
                        location=profile.name if profile else None,
                        started=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        queries=[q for q, _ in queries])
        raw: list[Result] = []
        jobs = {}
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for src in self.sources:
                if not src.available():
                    run.source_status[src.name] = f"skipped (set {src.env_key})"
                    continue
                if not src.per_query:
                    jobs[pool.submit(src.search_subject, subject, profile, self.limit)] = src.name
                    continue
                for q, is_local in queries:
                    if is_local and not src.uses_location_query:
                        continue
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
                    # keep "ok" if another query to the same source succeeded
                    if run.source_status.get(name) != "ok":
                        run.source_status[name] = f"error: {type(exc).__name__}: {exc}"[:200]
            for name, n in counts.items():
                if run.source_status.get(name) == "ok":
                    run.source_status[name] = f"ok ({n} raw results)"

        results = score_results(dedupe(raw), subject, profile)
        if self.fetch_pages:
            from .enrich import enrich_results
            # fetch pages that are at least loosely related, best first
            candidates = sorted((r for r in results if r.keyword_score > 0),
                                key=lambda r: r.relevance, reverse=True)[:self.fetch_pages]
            stats = enrich_results(candidates, subject, profile, workers=self.workers,
                                   timeout=min(self.timeout, 15))
            run.source_status["page_fetch"] = stats
        run.results = rank(results, subject, profile, min_keyword_score, location_only,
                           drop_unconfirmed)
        return run


def rank(results: list[Result], subject: Subject | str, profile: LocationProfile | None,
         min_keyword_score: float = 0.5, location_only: bool = False,
         drop_unconfirmed: bool = True) -> list[Result]:
    results = score_results(dedupe(results), subject, profile)
    results = [r for r in results if r.keyword_score >= min_keyword_score]
    if drop_unconfirmed:
        # A page we read in full that never mentions the name is a false match.
        results = [r for r in results if r.name_on_page is not False]
    if location_only and profile:
        results = [r for r in results if r.location_score > 0]
    results.sort(key=lambda r: (r.relevance, r.name_on_page is True, r.published or ""),
                 reverse=True)
    return results
