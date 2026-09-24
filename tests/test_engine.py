import json
from pathlib import Path

import docx
import pytest

from search_engine.cli import main
from search_engine.engine import SearchEngine, dedupe, keyword_score, normalize_url, rank
from search_engine.location import TEXAS
from search_engine.models import Result
from search_engine.sources.base import Source
from search_engine.sources import REGISTRY
from search_engine.sources.duckduckgo import parse_ddg_html
from search_engine.sources.rss_news import GoogleNews

KW = "Ana Andrei Philosophy"


def test_keyword_score_phrase_bonus():
    assert keyword_score(KW, "Ana Andrei teaches philosophy") == 1.0
    assert keyword_score(KW, "Ana Andrei on TikTok") == pytest.approx(0.667, abs=1e-3)
    assert keyword_score(KW, "Unrelated news") == 0.0


def test_texas_location_scoring():
    s, hits = TEXAS.score("Professor at Texas A&M University-Corpus Christi", "tamucc.edu")
    assert s > 0.6 and "Corpus Christi" in hits and "tamucc.edu" in hits
    assert TEXAS.score("A story from Ohio", "cleveland.com")[0] == 0
    # lowercase "tx" inside words/urls must not count as Texas
    assert TEXAS.score("see the txt file", "")[0] == 0


def test_normalize_and_dedupe():
    a = Result("A", "https://www.example.com/x/?utm_source=fb", "s1", snippet="short")
    b = Result("A", "https://example.com/x", "s2", snippet="a longer snippet")
    assert normalize_url(a.url) == normalize_url(b.url)
    merged = dedupe([a, b])
    assert len(merged) == 1 and merged[0].source == "s1, s2" and merged[0].snippet == "a longer snippet"


def test_platform_detection():
    assert Result("t", "https://www.tiktok.com/@x", "s").category == "Social"
    assert Result("t", "https://www.tiktok.com/@x", "s").platform == "TikTok"
    assert Result("t", "https://philosophy.tamucc.edu/p", "s").category == "Academic"


def test_rank_filters_and_orders():
    rs = [Result("Ana Andrei philosophy lecture", "https://a.com/1", "s", snippet="Houston"),
          Result("Ana Andrei philosophy", "https://b.com/2", "s"),
          Result("Weather today", "https://c.com/3", "s")]
    out = rank(rs, KW, TEXAS)
    assert [r.url for r in out] == ["https://a.com/1", "https://b.com/2"]
    assert [r.url for r in rank(rs, KW, TEXAS, location_only=True)] == ["https://a.com/1"]


def test_parse_ddg_html():
    html = """<div class="result"><a class="result__a"
      href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.tiktok.com%2F%40ana&rut=x">Ana on TikTok</a>
      <a class="result__snippet">Philosophy clips from Austin</a></div>"""
    [r] = parse_ddg_html(html, "tiktok", 10)
    assert r.url == "https://www.tiktok.com/@ana" and r.platform == "TikTok"


def test_google_news_rss(monkeypatch):
    rss = b"""<?xml version="1.0"?><rss><channel><item><title>Ana Andrei philosophy talk in Corpus Christi</title>
      <link>https://news.example.com/a</link><pubDate>Mon, 01 Sep 2026 10:00:00 GMT</pubDate>
      <description>&lt;b&gt;TAMUCC&lt;/b&gt; event</description></item></channel></rss>"""

    class Resp:
        content = rss
        def raise_for_status(self): pass

    src = GoogleNews()
    monkeypatch.setattr(src.session, "get", lambda *a, **k: Resp())
    [r] = src.search(KW, TEXAS, 10)
    assert r.published == "2026-09-01" and r.snippet == "TAMUCC event" and r.category == "News"


class _Fake(Source):
    name = "fake"
    def search(self, query, location, limit):
        return [Result(f"Ana Andrei philosophy ({query})", "https://x.edu/1", self.name, snippet="Dallas")]


class _Broken(Source):
    name = "broken"
    def search(self, query, location, limit):
        raise ConnectionError("blocked")


def test_engine_survives_broken_source(monkeypatch):
    monkeypatch.setitem(REGISTRY, "fake", _Fake)
    monkeypatch.setitem(REGISTRY, "broken", _Broken)
    run = SearchEngine(sources=["fake", "broken"], fetch_pages=0).search(KW, "Texas")
    assert len(run.results) == 1  # two queries, deduped
    assert run.source_status["fake"].startswith("ok")
    assert run.source_status["broken"].startswith("error")
    assert run.queries == [f"{KW} Texas", KW]


def test_keyed_sources_skip_without_key(monkeypatch):
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    run = SearchEngine(sources=["serpapi"], fetch_pages=0).search(KW, "Texas")
    assert "skipped" in run.source_status["serpapi"]


def test_cli_builds_docx_from_json(tmp_path):
    out = tmp_path / "r.docx"
    data = Path(__file__).parent.parent / "data" / "ana_andrei_philosophy_texas.json"
    assert main(["--from-json", str(data), "-o", str(out), "--json", str(tmp_path / "r.json")]) == 0
    text = "\n".join(p.text for p in docx.Document(out).paragraphs)
    assert "Ana Andrei Philosophy" in text and "Texas-linked" in text
    saved = json.loads((tmp_path / "r.json").read_text())
    assert saved["results"] and saved["results"][0]["relevance"] >= saved["results"][-1]["relevance"]
