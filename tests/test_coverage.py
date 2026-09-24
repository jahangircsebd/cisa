"""Tests for name variants, page reading and the added sources."""
from search_engine import enrich
from search_engine.engine import SearchEngine, rank
from search_engine.location import TEXAS
from search_engine.models import Result
from search_engine.sources import REGISTRY
from search_engine.sources.academic import Crossref, OpenAlex, SemanticScholar
from search_engine.sources.duckduckgo import DuckDuckGoWeb
from search_engine.sources.local import LocalNews, LocalWeb
from search_engine.sources.misc import Bluesky, Podcasts, Wikipedia
from search_engine.subject import Subject

KW = "Ana Andrei Philosophy"
ALIASES = ["Ana-Maria Andrei", "Dr. Andrei"]


class Resp:
    def __init__(self, json_data=None, text="", content=b"", headers=None):
        self._json, self.text, self.content = json_data, text, content
        self.headers = headers or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        pass


# --- name variants -------------------------------------------------------

def test_subject_topic_and_aliases():
    s = Subject(KW, ALIASES)
    assert s.aliases == ["Ana-Maria Andrei", "Ana Maria Andrei", "Dr. Andrei"]
    assert s.topic_tokens == ["philosophy"]
    # alias + topic is a full match; honorific is ignored
    assert s.score("Professor Andrei lectures on philosophy") == 1.0
    assert s.score("Ana-Maria Andrei, Department of Philosophy") == 1.0
    # name alone (no topic) is only a partial match
    assert s.score("Ana Maria Andrei on holiday") < 1.0


def test_subject_queries_include_aliases_and_location():
    qs = Subject(KW, ["Ana-Maria Andrei"]).queries("Texas")
    assert (f"{KW} Texas", True) in qs and (KW, False) in qs
    assert ('"Ana-Maria Andrei" philosophy Texas', True) in qs
    assert ('"Ana Maria Andrei" philosophy', False) in qs


def test_name_candidates_without_aliases():
    assert Subject(KW).name_candidates() == ["Ana Andrei Philosophy", "Ana Andrei"]
    assert Subject(KW).name_phrases() == ["Ana Andrei"]


def test_mentioned_in_keeps_keyword_name_and_ignores_punctuation():
    s = Subject(KW, ["Dr. Andrei"])
    assert s.mentioned_in("Syllabus by Ana Andrei")      # keyword name still counts
    assert s.mentioned_in("Contact Dr Andrei for office hours")  # no period
    assert s.mentioned_in("ANA-ANDREI profile")
    assert not s.mentioned_in("Andrei Rublev, painter")  # the name, not just a surname
    assert not s.mentioned_in("Banana Andreis")          # whole words only


def test_engine_sends_alias_queries_and_skips_location_for_some_sources(monkeypatch):
    seen = []

    class Rec(Wikipedia):
        name = "rec"
        def search(self, query, location, limit):
            seen.append(query)
            return []

    monkeypatch.setitem(REGISTRY, "rec", Rec)
    SearchEngine(sources=["rec"], fetch_pages=0).search(KW, "Texas", aliases=["Ana-Maria Andrei"])
    assert KW in seen and '"Ana-Maria Andrei" philosophy' in seen
    assert not any(q.endswith("Texas") for q in seen)  # uses_location_query = False


# --- page reading --------------------------------------------------------

PAGE = ("<html><head><title>Faculty</title><script>var x='Ana Andrei';</script></head><body>"
        + "Filler text. " * 60
        + "<p>Dr. Ana-Maria Andrei teaches philosophy of mind at Texas A&amp;M University-Corpus Christi.</p>"
        + "More filler. " * 60 + "</body></html>")


class FakeSession:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, **kw):
        body, ctype = self.pages[url]
        class R:
            headers = {"Content-Type": ctype}
            def raise_for_status(self): pass
            def iter_content(self, n): yield body
            def __enter__(self): return self
            def __exit__(self, *a): pass
        return R()


def test_enrich_finds_name_and_location_in_page_body():
    r = Result("Faculty", "https://example.edu/f", "web")
    enrich.enrich_one(FakeSession({r.url: (PAGE.encode(), "text/html")}), r,
                      Subject(KW, ALIASES), TEXAS, 5)
    assert r.name_on_page is True
    assert "Corpus Christi" in r.page_excerpt and len(r.page_excerpt) < 500  # context, not whole page
    [scored] = rank([r], Subject(KW, ALIASES), TEXAS)
    assert scored.keyword_score == 1.0 and "Corpus Christi" in scored.location_hits


def test_enrich_drops_readable_page_without_name_but_not_social():
    other = "<html><body>" + "An unrelated article about Houston weather. " * 30 + "</body></html>"
    news = Result("Ana Andrei philosophy", "https://news.example.com/a", "web")
    tiktok = Result("Ana Andrei philosophy", "https://www.tiktok.com/@x", "tiktok")
    sess = FakeSession({news.url: (other.encode(), "text/html"),
                        tiktok.url: (other.encode(), "text/html")})
    for r in (news, tiktok):
        enrich.enrich_one(sess, r, Subject(KW), TEXAS, 5)
    assert news.name_on_page is False and tiktok.name_on_page is None
    assert rank([news, tiktok], Subject(KW), TEXAS) == [tiktok]
    assert len(rank([news, tiktok], Subject(KW), TEXAS, drop_unconfirmed=False)) == 2


def test_enrich_records_fetch_errors():
    class Boom:
        def get(self, *a, **k):
            raise ConnectionError("x")
    r = Result("t", "https://a.com", "web")
    enrich.enrich_one(Boom(), r, Subject(KW), TEXAS, 5)
    assert r.page_status == "error: ConnectionError" and r.name_on_page is None


def test_build_excerpt_matches_hyphen_variants():
    text = "x " * 200 + "by Ana Maria Andrei in Austin" + " y" * 200
    ex = enrich.build_excerpt(text, ["Ana-Maria Andrei", "Austin"])
    assert "Ana Maria Andrei in Austin" in ex and len(ex) < 400


# --- new sources ---------------------------------------------------------

def test_openalex_author_then_works(monkeypatch):
    src = OpenAlex()
    def get(url, **kw):
        if url.endswith("/authors"):
            return Resp({"results": [
                {"id": "https://openalex.org/A1", "display_name": "Ana-Maria Andrei", "works_count": 3,
                 "last_known_institutions": [{"display_name": "Texas A&M University - Corpus Christi"}],
                 "topics": [{"display_name": "Philosophy of Mind"}]},
                {"id": "https://openalex.org/A2", "display_name": "Andrei Popescu"}]})
        return Resp({"results": [{"id": "W1", "title": "Transworld individuals", "doi": "https://doi.org/10.1/x",
                                  "publication_date": "2015-01-01",
                                  "primary_location": {"source": {"display_name": "Some Journal"}}}]})
    monkeypatch.setattr(src, "get", get)
    out = src.search_subject(Subject(KW), TEXAS, 10)
    assert [r.url for r in out] == ["https://openalex.org/A1", "https://doi.org/10.1/x"]
    assert "Corpus Christi" in out[1].snippet and out[1].category == "Academic"


def test_crossref_filters_fuzzy_author_matches(monkeypatch):
    src = Crossref()
    monkeypatch.setattr(src, "get", lambda *a, **k: Resp({"message": {"items": [
        {"DOI": "10.1/a", "title": ["Explanatory gap"], "author": [{"given": "Ana", "family": "Andrei"}],
         "issued": {"date-parts": [[2019, 5]]}, "container-title": ["Phil J"]},
        {"DOI": "10.1/b", "title": ["Other"], "author": [{"given": "Andrei", "family": "Rublev"}]}]}}))
    [r] = src.search_subject(Subject(KW), TEXAS, 10)
    assert r.url == "https://doi.org/10.1/a" and r.published == "2019-05"


def test_semantic_scholar(monkeypatch):
    src = SemanticScholar()
    monkeypatch.setattr(src, "get", lambda *a, **k: Resp({"data": [
        {"name": "Ana Andrei", "affiliations": ["Texas A&M University-Corpus Christi"],
         "url": "https://s2/a", "paperCount": 1,
         "papers": [{"title": "P", "year": 2020, "url": "https://s2/p", "venue": "V"}]}]}))
    out = src.search_subject(Subject(KW), TEXAS, 10)
    assert [r.url for r in out] == ["https://s2/a", "https://s2/p"]


def test_local_sources_restrict_to_location_sites(monkeypatch):
    queries = []
    rss = b"<rss><channel><item><title>Ana Andrei</title><link>https://caller.com/a</link></item></channel></rss>"
    news = LocalNews()
    news.min_interval = 0
    monkeypatch.setattr(news, "get", lambda url, **k: queries.append(url) or Resp(content=rss))
    out = news.search(KW, TEXAS, 5)
    assert all("site%3Acaller.com" in q or "site%3A" in q for q in queries)
    assert len(queries) == -(-len(TEXAS.news_domains) // 8) and out[0].source == "local_news"
    assert LocalNews().search(KW, None, 5) == []

    web = LocalWeb()
    web.min_interval = 0
    sent = []
    monkeypatch.setattr(web.session, "post", lambda url, data, **k: sent.append(data["q"]) or Resp(text=""))
    web.search(KW, TEXAS, 5)
    assert all("site:tamucc.edu" in q or "site:" in q for q in sent) and "site:tamucc.edu" in sent[0]


def _ddg_page(urls):
    return "".join(f'<div class="result"><a class="result__a" href="{u}">Ana Andrei</a></div>' for u in urls)


def test_ddg_reads_multiple_pages_and_survives_page_errors(monkeypatch):
    src = DuckDuckGoWeb()
    src.min_interval = 0
    pages = iter([_ddg_page(["https://a.com/1", "https://a.com/2"]), _ddg_page(["https://a.com/3"])])
    def post(url, data, **k):
        try:
            return Resp(text=next(pages))
        except StopIteration:
            raise ConnectionError("rate limited")
    monkeypatch.setattr(src.session, "post", post)
    assert [r.url for r in src.search(KW, None, 50)] == ["https://a.com/1", "https://a.com/2", "https://a.com/3"]


def test_wikipedia_podcasts_bluesky(monkeypatch):
    w = Wikipedia()
    monkeypatch.setattr(w, "get", lambda *a, **k: Resp({"query": {"search": [
        {"title": "Explanatory gap", "snippet": "<span>philosophy</span> of mind"}]}}))
    assert w.search(KW, None, 5)[0].url == "https://en.wikipedia.org/wiki/Explanatory_gap"

    p = Podcasts()
    monkeypatch.setattr(p, "get", lambda *a, **k: Resp({"results": [
        {"trackName": "Ep 1", "collectionName": "Philosophy Talk", "trackViewUrl": "https://pod/1",
         "releaseDate": "2026-01-02T00:00:00Z", "description": "Guest Ana Andrei"}]}))
    [ep] = p.search(KW, TEXAS, 5)
    assert ep.platform == "Podcast" and ep.category == "Media" and ep.published == "2026-01-02"

    monkeypatch.delenv("BLUESKY_HANDLE", raising=False)
    b = Bluesky()
    monkeypatch.setattr(b, "get", lambda url, **k: Resp({"posts": [
        {"uri": "at://did:plc:x/app.bsky.feed.post/abc", "author": {"handle": "tamucc.bsky.social"},
         "record": {"text": "Ana Andrei philosophy talk"}, "indexedAt": "2026-03-04T00:00:00Z"}]}))
    [post] = b.search(KW, None, 5)
    assert post.url == "https://bsky.app/profile/tamucc.bsky.social/post/abc" and post.category == "Social"


def test_throttle_spaces_requests_per_host(monkeypatch):
    from search_engine.sources import base
    sleeps = []
    clock = iter([100.0, 100.0, 100.1])
    monkeypatch.setattr(base.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(base.time, "sleep", sleeps.append)
    monkeypatch.setattr(base, "_host_next", {})
    base.throttle("https://h.test/a", 1.5)
    base.throttle("https://h.test/b", 1.5)
    base.throttle("https://other.test/", 1.5)
    assert sleeps == [1.5]
