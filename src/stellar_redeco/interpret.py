"""Reading what the client said about a complaint.

Since v0.2.0 an LLM reads the client's messages, the way a person would, and
answers two questions: is the claimant a client of the entity, and is the number
that made the collection call theirs. It must return the exact sentence each
answer rests on. The agent does not trust the reading blindly: the quote is
checked verbatim against the messages (evidence.unsupported), and the human
officer reviews every draft. Anything unclear goes back to the client.

    STELLAR_INTERPRETER=llm    use the LLM (needs ANTHROPIC_API_KEY)
    STELLAR_INTERPRETER=rules  phrase rules only (offline, deterministic; v0.1.x)
    unset                      llm if ANTHROPIC_API_KEY is set, otherwise rules
    STELLAR_LLM_MODEL          model id (default claude-sonnet-5-5)

Every interpreter returns:
    {"client_status": "client" | "not_client" | "unclear" | "conflict",
     "client_quote": str | None,
     "caller": "ours" | "not_ours" | "unclear" | None,   # None: complaint has no caller number
     "caller_quote": str | None,
     "by": "llm:<model>" | "rules"}
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from . import evidence

Interpreter = Callable[[dict[str, Any], list[str]], dict[str, Any]]


class InterpreterError(RuntimeError):
    """The reading could not be obtained (API down, bad answer). The agent fails closed."""


# --- offline fallback: phrase rules (v0.1.3) ---------------------------------

def rules(complaint: dict[str, Any], messages: list[str]) -> dict[str, Any]:
    found = [(evidence.client_status(x), x) for x in evidence.sentences(messages)]
    found = [(st, x) for st, x in found if st]
    if not found:
        status, quote = "unclear", None
    elif len({st for st, _ in found}) > 1:
        status, quote = "conflict", None
    else:
        status, quote = found[0]
    caller, caller_quote = _rules_caller(complaint, messages)
    return {"client_status": status, "client_quote": quote,
            "caller": caller, "caller_quote": caller_quote, "by": "rules"}


def _rules_caller(complaint, messages):
    digits = "".join(ch for ch in str(complaint.get("phone_caller", "")) if ch.isdigit())
    if not digits:
        return None, None
    for x in evidence.sentences(messages):
        if digits in "".join(ch for ch in x if ch.isdigit()):
            own = evidence.caller_ownership(x)
            if own:
                return own, x
    return "unclear", None


# --- LLM ------------------------------------------------------------------------

PROMPT = """You help a Mexican compliance officer answer a consumer complaint filed with CONDUSEF (REDECO).
Below are the messages the lender's operations team sent about complaint {folio}.
The claimant is {claimant}. The number that made the collection call is {caller}.

Read them as an experienced compliance analyst would. Spanish chat may lack accents
("si" can mean "sí" or "if"), have typos, or mention other complaints.

Answer only about complaint {folio}:
1. client_status: "not_client" if the team states the claimant is not their client
   (e.g. not in their system, data matches no client); "client" if they state the
   claimant is their client; "unclear" if they do not clearly state it (questions,
   doubts, conditions, "we are checking"); "conflict" if their messages contradict
   each other and no later message clearly settles it. If a later message clearly
   corrects an earlier one, use the correction.
2. caller: only if a caller number is given above. "not_ours" if they state that number
   does not belong to the entity (or its collection agencies); "ours" if they state it
   does; "unclear" otherwise. Use null if no caller number is given above.
3. For every answer other than "unclear"/"conflict"/null, copy the exact sentence or
   clause from the messages that states it, character for character, without
   correcting spelling, accents or punctuation.

Messages (oldest first):
{messages}

Reply with JSON only:
{{"client_status": "...", "client_quote": "..." or null, "caller": "..." or null, "caller_quote": "..." or null}}"""

API_URL = "https://api.anthropic.com/v1/messages"


def _post(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    import httpx
    r = httpx.post(API_URL, json=payload, timeout=60,
                   headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                            "content-type": "application/json"})
    r.raise_for_status()
    return r.json()


def llm(model: str | None = None, api_key: str | None = None,
        post: Callable[[dict[str, Any], str], dict[str, Any]] = _post) -> Interpreter:
    model = model or os.environ.get("STELLAR_LLM_MODEL", "claude-sonnet-5-5")
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def interpret(complaint: dict[str, Any], messages: list[str]) -> dict[str, Any]:
        caller = complaint.get("phone_caller") or None
        prompt = PROMPT.format(folio=complaint.get("folio"), claimant=complaint.get("claimant", "(unknown)"),
                               caller=caller or "not given",
                               messages="\n".join(f"[{i + 1}] {m}" for i, m in enumerate(messages)))
        try:
            resp = post({"model": model, "max_tokens": 400, "temperature": 0,
                         "messages": [{"role": "user", "content": prompt}]}, key)
            text = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
            out = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
        except Exception as exc:  # network, HTTP, or an answer that is not JSON
            raise InterpreterError(f"{type(exc).__name__}: {exc}") from exc
        if out.get("client_status") not in ("client", "not_client", "unclear", "conflict"):
            raise InterpreterError(f"unexpected client_status {out.get('client_status')!r}")
        if not caller:
            out["caller"], out["caller_quote"] = None, None
        elif out.get("caller") not in ("ours", "not_ours", "unclear"):
            raise InterpreterError(f"unexpected caller {out.get('caller')!r}")
        return {"client_status": out["client_status"], "client_quote": out.get("client_quote"),
                "caller": out.get("caller"), "caller_quote": out.get("caller_quote"), "by": f"llm:{model}"}

    return interpret


def default() -> Interpreter:
    mode = os.environ.get("STELLAR_INTERPRETER", "").lower()
    if mode == "rules" or (not mode and not os.environ.get("ANTHROPIC_API_KEY")):
        return rules
    return llm()
