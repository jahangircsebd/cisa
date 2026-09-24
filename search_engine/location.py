"""Location profiles used to geo-tag results (e.g. "Texas")."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class LocationProfile:
    name: str
    query_term: str                       # appended to search queries
    terms: list[str]                      # strong signals (state name, abbreviations)
    places: list[str] = field(default_factory=list)       # cities, counties, institutions
    domains: list[str] = field(default_factory=list)      # local outlets / institutions
    country_code: str = "US"

    def score(self, text: str, domain: str = "") -> tuple[float, list[str]]:
        """Return (0..1 score, matched terms) for how strongly text relates to this place."""
        hits: list[str] = []
        for term in self.terms + self.places:
            # All-caps abbreviations (TX, SMU) must match case-sensitively.
            flags = 0 if term.isupper() else re.IGNORECASE
            if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, flags):
                hits.append(term)
        for dom in self.domains:
            if domain == dom or domain.endswith("." + dom):
                hits.append(dom)
        if not hits:
            return 0.0, []
        strong = any(h in self.terms or h in self.domains for h in hits)
        score = min(1.0, (0.6 if strong else 0.4) + 0.15 * (len(hits) - 1))
        return round(score, 3), sorted(set(hits))


TEXAS = LocationProfile(
    name="Texas",
    query_term="Texas",
    terms=["Texas", "TX", "Tex."],
    places=[
        "Houston", "Dallas", "Austin", "San Antonio", "Fort Worth", "El Paso",
        "Corpus Christi", "Arlington", "Plano", "Lubbock", "Laredo", "Irving",
        "Garland", "Frisco", "McKinney", "Amarillo", "Brownsville", "Killeen",
        "Waco", "College Station", "Denton", "Midland", "Odessa", "Beaumont",
        "Tyler", "Abilene", "San Marcos", "Galveston", "McAllen", "Edinburg",
        "Kingsville", "Victoria", "Round Rock", "Sugar Land", "The Woodlands",
        "Texas A&M", "TAMUCC", "UT Austin", "Rice University", "Baylor",
        "Texas Tech", "SMU", "TCU", "UTSA", "UTEP", "Harris County",
        "Travis County", "Bexar County", "Nueces County", "Dallas County",
    ],
    domains=[
        "tamucc.edu", "tamu.edu", "utexas.edu", "rice.edu", "baylor.edu", "ttu.edu",
        "smu.edu", "tcu.edu", "utsa.edu", "utep.edu", "uh.edu", "unt.edu", "txstate.edu",
        "texastribune.org", "houstonchronicle.com", "dallasnews.com", "statesman.com",
        "expressnews.com", "caller.com", "kiiitv.com", "kristv.com", "kztv10.com",
        "chron.com", "star-telegram.com", "texasmonthly.com", "kxan.com", "khou.com",
        "wfaa.com", "ksat.com", "texas.gov",
    ],
)

PROFILES = {"texas": TEXAS}


def get_profile(name: str | None) -> LocationProfile | None:
    if not name:
        return None
    key = name.strip().lower()
    if key in PROFILES:
        return PROFILES[key]
    # Generic fallback: any other place name still works, just with fewer signals.
    return LocationProfile(name=name.strip(), query_term=name.strip(), terms=[name.strip()])
