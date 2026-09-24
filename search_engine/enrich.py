"""Open each result page and read its full text.

Search snippets are short, so a page may mention Corpus Christi or the
person's full name only in its body. We keep short excerpts around every
name/topic/location match (not the whole page) so the scores can be
recomputed later from saved JSON.
"""
from __future__ import annotations

import io
import logging
import re
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup

from .location import LocationProfile
from .models import SOCIAL_PLATFORMS, Result
from .sources.base import USER_AGENT
from .subject import Subject

log = logging.getLogger(__name__)

MAX_BYTES = 5_000_000
WINDOW = 160          # characters kept either side of a match
MAX_EXCERPT = 1500
MIN_TEXT_FOR_VERDICT = 400  # below this the page is probably a login wall / JS app


def html_to_text(html: bytes | str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    meta = " ".join(m.get("content", "") for m in soup.find_all("meta")
                    if m.get("name") in ("description", "keywords")
                    or m.get("property") in ("og:title", "og:description"))
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "form"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    return re.sub(r"\s+", " ", f"{title} {meta} {soup.get_text(' ', strip=True)}")


def pdf_to_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return " ".join((p.extract_text() or "") for p in reader.pages[:30])
    except BaseException:  # noqa: BLE001 - broken crypto deps can raise PanicException
        pass
    try:
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            return " ".join(page.get_text() for page in list(doc)[:30])
    except Exception:
        return ""


def match_terms(subject: Subject, location: LocationProfile | None) -> list[str]:
    terms = list(subject.name_phrases()) + subject.topic_tokens
    if not subject.aliases:
        terms += [t for t in subject.keyword.split()[2:]]
    if location:
        terms += location.terms + location.places
    return [t for t in terms if len(t) > 1]


def build_excerpt(text: str, terms: list[str]) -> str:
    """Merge ±WINDOW-char windows around every term match, capped at MAX_EXCERPT."""
    spans: list[tuple[int, int]] = []
    for term in terms:
        flags = 0 if term.isupper() else re.IGNORECASE
        pat = r"(?<!\w)" + re.escape(term).replace(r"\-", r"[-\s]").replace(r"\ ", r"[-\s]+") + r"(?!\w)"
        for m in re.finditer(pat, text, flags):
            spans.append((max(0, m.start() - WINDOW), min(len(text), m.end() + WINDOW)))
            if len(spans) > 60:
                break
    if not spans:
        return ""
    spans.sort()
    merged = [spans[0]]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    out, total = [], 0
    for s, e in merged:
        piece = text[s:e].strip()
        out.append(piece)
        total += len(piece)
        if total >= MAX_EXCERPT:
            break
    return " … ".join(out)[:MAX_EXCERPT]


def fetch_text(session: requests.Session, url: str, timeout: float) -> str:
    with session.get(url, timeout=timeout, stream=True, allow_redirects=True) as resp:
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "").lower()
        data = b""
        for chunk in resp.iter_content(65536):
            data += chunk
            if len(data) > MAX_BYTES:
                break
    if "pdf" in ctype or url.lower().endswith(".pdf") or data[:5] == b"%PDF-":
        return re.sub(r"\s+", " ", pdf_to_text(data))
    if "html" in ctype or "xml" in ctype or not ctype:
        return html_to_text(data)
    if ctype.startswith("text/"):
        return data.decode("utf-8", "replace")
    return ""


def enrich_one(session, r: Result, subject: Subject, location, timeout: float) -> None:
    try:
        text = fetch_text(session, r.url, timeout)
    except Exception as exc:
        r.page_status = f"error: {type(exc).__name__}"
        return
    found = subject.mentioned_in(text)
    # Only call a page a non-match when we could actually read it: social sites
    # and short pages are often login walls or JavaScript apps.
    if found:
        r.name_on_page = True
    elif len(text) >= MIN_TEXT_FOR_VERDICT and r.platform not in SOCIAL_PLATFORMS:
        r.name_on_page = False
    r.page_excerpt = build_excerpt(text, match_terms(subject, location))
    if not r.snippet and r.page_excerpt:
        r.snippet = r.page_excerpt[:300]
    r.page_status = f"ok ({len(text)} chars)"


def enrich_results(results: list[Result], subject: Subject, location: LocationProfile | None,
                   workers: int = 8, timeout: float = 15) -> str:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    adapter = requests.adapters.HTTPAdapter(pool_connections=workers, pool_maxsize=workers)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda r: enrich_one(session, r, subject, location, timeout), results))
    ok = sum(1 for r in results if (r.page_status or "").startswith("ok"))
    confirmed = sum(1 for r in results if r.name_on_page)
    rejected = sum(1 for r in results if r.name_on_page is False)
    return (f"ok ({ok}/{len(results)} pages read; name confirmed on {confirmed}, "
            f"{rejected} dropped as not mentioning the name)")
