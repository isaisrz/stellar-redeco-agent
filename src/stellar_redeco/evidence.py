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


# --- polarity of the client's statements (v0.1.2) ---------------------------
# v0.1.0-0.1.1 matched the substring "es cliente", so "no es cliente" produced a
# draft saying the claimant IS a client (found by the HW9 cold-start run). Now the
# statement's polarity is classified; anything not recognized is treated as
# unanswered (the agent asks again or blocks), never guessed.

_NEG_CLIENT = re.compile(
    r"\bno (es|era|son) (nuestr[oa]s? )?client|\bno corresponden?\b.*\bclient"
    r"|\bningun client|\bno (lo |la )?(tenemos|encontramos) (registrad|como client|en (el|nuestro) sistema)"
    r"|\bno aparece|\bno (se encuentra|esta) registrad")
_POS_CLIENT = re.compile(r"\b(si )?(es|era) (nuestr[oa] )?client")
_NEG_CALLER = re.compile(r"\bno (pertenece|es (nuestro|de la entidad|de nosotros)|lo reconocemos|corresponde)|\bdesconoc")
_POS_CALLER = re.compile(r"\b(si )?(pertenece|es nuestro|es de la entidad|corresponde)")


# "si" without an accent is both "yes" (typed without the accent) and "if/whether".
# A statement is hedged -- not an answer -- when it is a question, when "si" follows
# a verb of doubt or checking ("no sé si es cliente", "vamos a confirmar si..."),
# or when an unaccented "si es ..." opens a condition ("si es cliente, lo buscamos").
_DOUBT = re.compile(r"\b(se|sabemos|sabe|saber|sabria|revisar|revisamos|revisando|confirmar|confirmamos|"
                    r"confirmando|verificar|verificamos|verificando|checar|checamos|checando|ver|vemos|"
                    r"preguntar|preguntamos|averiguar|averiguamos|consultar|consultamos|validar|validamos)"
                    r"( [a-z]+){0,3} si\b")
_COND_TAIL = re.compile(r",|\b(entonces|se|hay|habria|podemos|vamos|tendriamos|tenemos que|debe|deberia|"
                        r"procede|aplica|mandamos|enviamos|contestamos|respondemos|revisamos|buscamos|avisamos)\b")


def _hedged(sentence: str, key: str) -> bool:
    raw = unicodedata.normalize("NFC", sentence or "").lower()
    if "?" in raw or "¿" in raw or _DOUBT.search(norm(sentence)):
        return True
    m = re.search(r"(?<![\wí])si (es|era|pertenece) " + key, raw)  # unaccented "si" only
    return bool(m and _COND_TAIL.search(raw[m.end():]))


def client_status(sentence: str) -> str | None:
    """'not_client', 'client' or None (not a recognizable statement)."""
    if _hedged(sentence, r"(nuestr[oa] )?client"):
        return None
    n = norm(sentence)
    if _NEG_CLIENT.search(n):
        return "not_client"
    if _POS_CLIENT.search(n):
        return "client"
    return None


def caller_ownership(sentence: str) -> str | None:
    """'not_ours', 'ours' or None for a sentence that mentions the caller number."""
    if _hedged(sentence, r""):
        return None
    n = norm(sentence)
    if _NEG_CALLER.search(n):
        return "not_ours"
    if _POS_CALLER.search(n):
        return "ours"
    return None


def sentences(sources: list[str]) -> list[str]:
    return [s.strip() for src in sources for s in re.split(r"(?<=[.;])\s+|\n+", src) if s.strip()]
