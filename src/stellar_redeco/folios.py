"""Folio matching. Clients often retype REDECO folios with a one-digit slip
(e.g. 34424 for 34824). We link a chat folio to a portal folio only when it is
exactly one edit away (substitution, adjacent transposition, insertion or
deletion) from ONE portal folio; if two are equally close we abstain."""
from __future__ import annotations

import re

FOLIO_RE = re.compile(r"\b(\d{4})[/-]REDECO[/-](\d{3,7})\b")


def find_folios(text: str) -> list[str]:
    return [f"{a}/REDECO/{b}" for a, b in FOLIO_RE.findall(text or "")]


def one_edit(a: str, b: str) -> bool:
    if a == b:
        return False
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        return len(d) == 1 or (len(d) == 2 and d[1] == d[0] + 1
                               and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]])
    if abs(len(a) - len(b)) != 1:
        return False
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def link(chat_folio: str, portal_folios: set[str]) -> str | None:
    if chat_folio in portal_folios:
        return chat_folio
    num = chat_folio.split("/")[-1]
    cands = [f for f in portal_folios if one_edit(num, f.split("/")[-1])]
    return cands[0] if len(cands) == 1 else None
