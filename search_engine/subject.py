"""What we are searching for: the main keyword plus alternative names (aliases).

Given keyword "Ana Andrei Philosophy" and alias "Ana-Maria Andrei", the keyword
words that don't appear in any alias ("philosophy") are treated as the *topic*.
Each alias is then searched and scored together with that topic, so
"Ana-Maria Andrei philosophy" counts as a full match.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

STOPWORDS = {"the", "a", "an", "of", "and", "or", "in", "on", "for", "to",
             # honorifics: "Dr. Andrei" should match pages saying "Professor Andrei"
             "dr", "prof", "professor", "mr", "ms", "mrs"}


def normalize_text(text: str) -> str:
    """Lowercase and treat hyphens/underscores as spaces (Ana-Maria == Ana Maria)."""
    return re.sub(r"\s+", " ", re.sub(r"[-_‐-―]", " ", text.lower()))


def plain(text: str) -> str:
    """normalize_text with punctuation (except &) turned into spaces: 'Dr. Andrei' -> 'dr andrei'."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w&]+", " ", normalize_text(text))).strip()


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[\w&']+", normalize_text(text)) if t not in STOPWORDS]


def phrase_score(phrase_tokens: list[str], text: str) -> float:
    """Share of phrase words present in text, +0.2 bonus for the exact phrase."""
    if not phrase_tokens:
        return 0.0
    norm = normalize_text(text)
    found = sum(1 for t in phrase_tokens if re.search(r"\b" + re.escape(t) + r"\b", norm))
    score = found / len(phrase_tokens)
    if " ".join(phrase_tokens) in " ".join(tokens(norm)):
        score += 0.2
    return round(min(1.0, score), 3)


def hyphen_variants(name: str) -> list[str]:
    """'Ana-Maria Andrei' -> ['Ana-Maria Andrei', 'Ana Maria Andrei']."""
    out = [name]
    if "-" in name:
        out.append(name.replace("-", " "))
    return out


@dataclass
class Subject:
    keyword: str
    aliases: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        seen, clean = {self.keyword.lower()}, []
        for a in self.aliases:
            for v in hyphen_variants(a.strip()):
                if v and v.lower() not in seen:
                    seen.add(v.lower())
                    clean.append(v)
        self.aliases = clean

    @property
    def topic_tokens(self) -> list[str]:
        if not self.aliases:
            return []
        alias_toks = {t for a in self.aliases for t in tokens(a)}
        return [t for t in tokens(self.keyword) if t not in alias_toks]

    @property
    def topic(self) -> str:
        return " ".join(self.topic_tokens)

    def phrases(self) -> list[list[str]]:
        """Token lists that each count as a full match of the subject."""
        out = [tokens(self.keyword)]
        out += [tokens(a) + [t for t in self.topic_tokens if t not in tokens(a)]
                for a in self.aliases]
        return [p for p in out if p]

    def score(self, text: str) -> float:
        return max((phrase_score(p, text) for p in self.phrases()), default=0.0)

    def name_candidates(self) -> list[str]:
        """Likely person/entity names, for sources that look up authors.

        Aliases first; then the keyword with trailing words dropped
        ("Ana Andrei Philosophy" -> "Ana Andrei"), since we can't know which
        words of the keyword are the name.
        """
        out = list(self.aliases)
        words = self.keyword.split()
        for n in range(len(words), 1, -1):
            cand = " ".join(words[:n])
            if cand not in out:
                out.append(cand)
        return out

    def name_phrases(self) -> list[str]:
        """Phrases whose presence on a page confirms the subject is mentioned:
        every alias, plus the name taken from the keyword (its first two words
        when it has more, e.g. "Ana Andrei" from "Ana Andrei Philosophy")."""
        words = self.keyword.split()
        from_keyword = " ".join(words[:2]) if len(words) > 2 else self.keyword
        return self.aliases + ([from_keyword] if from_keyword not in self.aliases else [])

    def mentioned_in(self, text: str) -> bool:
        """True if any name phrase appears in text, ignoring case and punctuation."""
        page = f" {plain(text)} "
        return any(f" {plain(n)} " in page for n in self.name_phrases())

    def queries(self, location_term: str | None) -> list[tuple[str, bool]]:
        """(query, is_location_qualified) pairs.

        Location-qualified first, plus bare versions to catch items that
        mention a city (e.g. Corpus Christi) without naming the state.
        """
        bases = [self.keyword] + [f'"{a}" {self.topic}'.strip() for a in self.aliases]
        out: list[tuple[str, bool]] = []
        for b in bases:
            if location_term:
                out.append((f"{b} {location_term}", True))
            out.append((b, False))
        return out
