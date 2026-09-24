"""Command line interface.

Examples:
  python -m search_engine "Ana Andrei Philosophy" --location Texas
  python -m search_engine "Ana Andrei Philosophy" -l Texas -a "Ana-Maria Andrei" -a "Dr. Andrei"
  python -m search_engine "Ana Andrei Philosophy" --location Texas --sources google_news,tiktok
  python -m search_engine --from-json data/results.json          # rebuild report from saved results
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from .engine import SearchEngine, SearchRun, rank
from .location import get_profile
from .report import build_report
from .sources import DEFAULT_SOURCES, REGISTRY
from .subject import Subject


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:60]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="search_engine", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("keyword", nargs="?", help="keyword or phrase to search for")
    ap.add_argument("-l", "--location", help="location focus, e.g. Texas")
    ap.add_argument("-a", "--alias", action="append", default=[],
                    help="another name for the subject (repeatable), e.g. -a \"Ana-Maria Andrei\"")
    ap.add_argument("-s", "--sources", help="comma-separated sources (default: all). "
                    f"Available: {', '.join(sorted(REGISTRY))}")
    ap.add_argument("-n", "--limit", type=int, default=30, help="max results per source per query")
    ap.add_argument("--min-score", type=float, default=0.5, help="min keyword score 0..1 (default 0.5)")
    ap.add_argument("--location-only", action="store_true",
                    help="keep only results with a location signal")
    ap.add_argument("--fetch-limit", type=int, default=60,
                    help="open and read up to this many result pages (default 60)")
    ap.add_argument("--no-fetch", action="store_true", help="don't open result pages (faster)")
    ap.add_argument("--keep-unconfirmed", action="store_true",
                    help="keep results whose page was read but never mentions the name")
    ap.add_argument("-o", "--output", help="output .docx path (default: reports/<keyword>_<date>.docx)")
    ap.add_argument("--json", help="also save raw results as JSON to this path")
    ap.add_argument("--from-json", help="skip searching; build the report from a saved JSON run")
    ap.add_argument("--notes", help="analyst notes to include in the executive summary")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    if args.from_json:
        data = json.loads(Path(args.from_json).read_text())
        run = SearchRun.from_dict(data)
        if args.alias:
            run.aliases = Subject(run.keyword, run.aliases + args.alias).aliases
        run.results = rank(run.results, run.subject, get_profile(run.location),
                           args.min_score, args.location_only, not args.keep_unconfirmed)
        notes = args.notes or data.get("notes")
    elif args.keyword:
        sources = args.sources.split(",") if args.sources else DEFAULT_SOURCES
        engine = SearchEngine(sources=[s.strip() for s in sources], limit_per_source=args.limit,
                              fetch_pages=0 if args.no_fetch else args.fetch_limit)
        run = engine.search(args.keyword, args.location, args.min_score, args.location_only,
                            aliases=args.alias, drop_unconfirmed=not args.keep_unconfirmed)
        notes = args.notes
    else:
        ap.error("provide a keyword or --from-json")

    for name, status in sorted(run.source_status.items()):
        print(f"  [{name}] {status}", file=sys.stderr)

    out = args.output or f"reports/{slug(run.keyword)}_{slug(run.location or 'global')}_" \
                         f"{datetime.now():%Y%m%d_%H%M}.docx"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(run.to_dict(), indent=2, ensure_ascii=False))
    build_report(run, out, notes)
    print(f"{len(run.results)} results -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
