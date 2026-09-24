"""Scholarly databases: find the person as an author and list their publications.

All three are free and need no key. They are called once per run with the
whole Subject (not per query string), because they search by author name.
"""
from __future__ import annotations

from ..models import Result
from ..subject import tokens
from .base import Source


def _name_matches(candidate: str, author_name: str) -> bool:
    """Every word of the searched name appears in the author's name."""
    have = set(tokens(author_name))
    return bool(have) and all(t in have for t in tokens(candidate))


class _AuthorSource(Source):
    category = "Academic"
    per_query = False
    max_authors = 3

    def search_subject(self, subject, location, limit):
        out: list[Result] = []
        for name in subject.name_candidates():
            found = self.search_name(name, limit)
            out += found
            if found:  # the most specific name that returns something wins
                break
        return out[:limit]

    def search_name(self, name: str, limit: int) -> list[Result]:
        raise NotImplementedError


class OpenAlex(_AuthorSource):
    name = "openalex"
    base = "https://api.openalex.org"

    def search_name(self, name, limit):
        authors = self.get(f"{self.base}/authors", params={"search": name, "per-page": 10}).json()
        out = []
        for a in authors.get("results", []):
            if not _name_matches(name, a.get("display_name", "")):
                continue
            insts = [i.get("display_name", "") for i in a.get("last_known_institutions") or []]
            aid = a["id"].rsplit("/", 1)[-1]
            topics = [t.get("display_name", "") for t in (a.get("topics") or [])[:5]]
            out.append(Result(
                title=f"{a['display_name']} – author profile (OpenAlex)",
                url=a.get("orcid") or a["id"], source=self.name, category="Academic",
                snippet=f"Institution: {', '.join(insts) or 'unknown'}. "
                        f"{a.get('works_count', 0)} works. Topics: {', '.join(topics)}",
            ))
            works = self.get(f"{self.base}/works", params={
                "filter": f"author.id:{aid}", "per-page": min(limit, 50),
                "sort": "publication_date:desc"}).json()
            for w in works.get("results", []):
                venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
                out.append(Result(
                    title=w.get("title") or "(untitled)",
                    url=w.get("doi") or (w.get("primary_location") or {}).get("landing_page_url") or w["id"],
                    source=self.name, category="Academic", published=w.get("publication_date"),
                    snippet=f"By {a['display_name']} ({', '.join(insts) or 'institution unknown'})"
                            + (f". Published in {venue}" if venue else ""),
                ))
            if len(out) >= limit or len([r for r in out if "author profile" in r.title]) >= self.max_authors:
                break
        return out


class Crossref(_AuthorSource):
    name = "crossref"

    def search_name(self, name, limit):
        data = self.get("https://api.crossref.org/works", params={
            "query.author": name, "rows": min(limit, 50),
            "select": "DOI,title,author,container-title,issued,URL"}).json()
        out = []
        for it in data.get("message", {}).get("items", []):
            authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in it.get("author", [])]
            if not any(_name_matches(name, a) for a in authors):
                continue  # Crossref's author search is fuzzy
            parts = (it.get("issued", {}).get("date-parts") or [[None]])[0]
            date = "-".join(f"{p:02d}" for p in parts if p) if parts and parts[0] else None
            affs = [af.get("name", "") for a in it.get("author", []) for af in a.get("affiliation", [])]
            out.append(Result(
                title=(it.get("title") or ["(untitled)"])[0],
                url=it.get("URL") or f"https://doi.org/{it['DOI']}", source=self.name,
                category="Academic", published=date,
                snippet=f"Authors: {', '.join(authors)}. "
                        f"{(it.get('container-title') or [''])[0]}"
                        + (f". Affiliation: {'; '.join(affs)}" if affs else ""),
            ))
        return out


class SemanticScholar(_AuthorSource):
    name = "semantic_scholar"
    min_interval = 1.1  # keyless limit is about 1 request/second
    base = "https://api.semanticscholar.org/graph/v1"

    def search_name(self, name, limit):
        data = self.get(f"{self.base}/author/search", params={
            "query": name, "limit": 5,
            "fields": "name,affiliations,url,paperCount,papers.title,papers.year,papers.url,papers.venue",
        }).json()
        out = []
        for a in data.get("data", [])[:self.max_authors]:
            if not _name_matches(name, a.get("name", "")):
                continue
            affs = ", ".join(a.get("affiliations") or []) or "affiliation unknown"
            out.append(Result(title=f"{a['name']} – author profile (Semantic Scholar)",
                              url=a.get("url", ""), source=self.name, category="Academic",
                              snippet=f"{affs}. {a.get('paperCount', 0)} papers."))
            for p in (a.get("papers") or [])[:limit]:
                if p.get("url"):
                    out.append(Result(title=p.get("title") or "(untitled)", url=p["url"],
                                      source=self.name, category="Academic",
                                      published=str(p["year"]) if p.get("year") else None,
                                      snippet=f"By {a['name']} ({affs}). {p.get('venue') or ''}"))
        return out

