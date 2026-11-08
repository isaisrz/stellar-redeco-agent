"""Grounding check: every factual claim in a draft about the entity's records
must quote, verbatim, a message the client actually sent. Matching ignores case,
punctuation and accent encoding (iPhones send decomposed accents)."""
from __future__ import annotations

import re
import unicodedata


def norm(text: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", text or "")
                if not unicodedata.combining(c))
    return re.sub(r"[\W_]+", " ", t.lower()).strip()


def unsupported(citations: list[dict], sources: list[str]) -> list[dict]:
    base = " ".join(norm(s) for s in sources)
    return [c for c in citations if len(norm(c.get("quote", ""))) < 8
            or norm(c["quote"]) not in base]


def find_sentence(sources: list[str], *needles: str) -> str | None:
    """First sentence in the client's messages containing all needles."""
    for s in sources:
        for sent in re.split(r"(?<=[.;])\s+|\n+", s):
            n = norm(sent)
            if all(norm(x) in n for x in needles):
                return sent.strip()
    return None
