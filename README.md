# Keyword Media Search Engine

Type a keyword or phrase. The tool searches news, the web and social media (TikTok, YouTube,
Instagram, Facebook, X, LinkedIn, Reddit) for it. It can focus on one place, such as **Texas**,
and writes a **Word (.docx) report**.

## Quick start

```bash
pip install -r requirements.txt

# Search every source, focus on Texas, write a Word report into reports/
python -m search_engine "Ana Andrei Philosophy" --location Texas

# Also search other forms of the name (recommended for people)
python -m search_engine "Ana Andrei Philosophy" -l Texas -a "Ana-Maria Andrei" -a "Dr. Andrei"

# Keep only results with a Texas signal, and also save the raw data as JSON
python -m search_engine "Ana Andrei Philosophy" -l Texas --location-only --json data/run.json

# Search only a few sources
python -m search_engine "Ana Andrei Philosophy" -l Texas -s google_news,tiktok,youtube

# Rebuild a report from saved JSON (no new search)
python -m search_engine --from-json data/ana_andrei_philosophy_texas.json
```

Run `python -m search_engine -h` to see every option.

A full run takes a few minutes, because the tool spaces out its requests so free
search sites don't block it. Use `-s` to search fewer sources, or `--no-fetch` to skip
reading the result pages.

## Name variants (`-a` / `--alias`)

Pages often use a different form of a name, like "Ana-Maria Andrei", "Ana Maria Andrei"
or "Dr. Andrei". Give each form with `-a`. The tool then:

- Searches every source for each form, with and without the location.
- Treats the keyword words that aren't part of any name as the **topic** (here,
  "philosophy"), and searches each name form together with that topic.
- Counts "name form + topic" as a full match when scoring. The hyphen and space
  versions of a name are covered automatically, and titles like Dr. and Prof. are ignored.

## Reading the result pages

After searching, the tool opens the top 60 results (change this with `--fetch-limit`)
and reads the full page, including PDFs such as CVs. This helps in two ways:

- **Better Texas detection:** a page that mentions Corpus Christi only in its body still
  gets tagged as Texas.
- **Fewer wrong people:** if a page could be read but never mentions the name, it is
  dropped. Social media pages are never dropped this way, because they often hide their
  text behind a login. To keep dropped pages, use `--keep-unconfirmed`.

The report shows "name confirmed on page" and the relevant passage for each result.

## Sources

| Source | What it covers | Needs a key? |
|---|---|---|
| `google_news`, `bing_news` | News articles, through public RSS search feeds | No |
| `gdelt` | GDELT global news index, limited to US outlets | No |
| `web` | General web search (DuckDuckGo, first 3 pages of results) | No |
| `tiktok`, `youtube`, `instagram`, `facebook`, `x`, `linkedin` | Public posts and profiles, found with `site:` web searches | No |
| `reddit_api` | Reddit posts | No |
| `local_news` | Google News, but only on Texas news sites (Texas Tribune, Caller-Times, Houston Chronicle, KIII, KRIS, ...) | No |
| `local_web` | Web search, but only on Texas university and government sites (TAMUCC, UT, Texas A&M, texas.gov, ...) | No |
| `openalex`, `crossref`, `semantic_scholar` | Academic databases: finds the person as an author, their institution and their publications | No |
| `wikipedia` | Wikipedia articles | No |
| `podcasts` | Podcast episodes (Apple Podcasts directory) | No |
| `bluesky` | Bluesky posts | Optional: `BLUESKY_HANDLE` + `BLUESKY_APP_PASSWORD` (Bluesky may refuse searches without a login) |
| `youtube_api` | YouTube Data API v3 | `YOUTUBE_API_KEY` |
| `serpapi` | Google results for a real location (e.g. "Texas, United States") | `SERPAPI_KEY` |
| `google_cse` | Google Programmable Search | `GOOGLE_CSE_KEY` + `GOOGLE_CSE_ID` |

A source that needs a key is skipped until you set its environment variable. If one source fails
(blocked or rate-limited), the run continues with the rest, and the report shows each source's status.

**About TikTok and other social media:** these platforms have no open keyword-search API, so the
tool finds their public, indexed content through web search. For better coverage, set an API key
(SerpAPI or YouTube). A name match on social media may be a different person, so check it before
you rely on it.

## How the Texas focus works

1. Every source gets two queries per name form: one with "Texas" added and one without.
   The query without "Texas" catches items that name a city but not the state. The local
   sources search only Texas news outlets and Texas institutions.
2. Each result gets a **location score**. It rises when the result mentions Texas or `TX`, a Texas
   city or county (Houston, Corpus Christi, ...), a Texas university (Texas A&M, TAMUCC, UT
   Austin, ...), or comes from a Texas news site or university domain.
3. **Relevance** = 0.6 × keyword score + 0.4 × location score.
4. The Texas check uses the title, the snippet and, when the page was read, the text on
   the page itself.
5. The report puts Texas-linked results first, then other relevant results. Within each group,
   results are sorted into News, Social, Academic and Web.

To focus on a different place, pass any name (`-l Ohio`). For a detailed profile like the Texas
one, add a `LocationProfile` in `search_engine/location.py`.

## The Word report

1. Summary table: keyword, location, date and the queries used
2. Executive summary, with optional analyst notes (`--notes`)
3. Results broken down by category, top domains and location signals found
4. Detailed results: title, platform or domain, date, relevance, snippet and a clickable link
5. Sources and methodology, including each source's status

## First report: "Ana Andrei Philosophy" (Texas)

`reports/Ana_Andrei_Philosophy_Texas_Report.docx` was built from web search results collected
on 2026-09-24 (`data/ana_andrei_philosophy_texas.json`). Run the command above on your own
machine to refresh it with live news and social media results.

## Tests

```bash
pip install pytest && python -m pytest -q
```
