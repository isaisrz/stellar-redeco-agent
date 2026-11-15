"""The REDECO compliance agent: a state machine whose reading of the client's
messages comes from an interpreter (an LLM, or offline phrase rules; see
interpret.py) and is verified against the messages before any draft.

It does the compliance officer's preparation work and nothing more:
read the regulator portal, open one case per complaint, link the client's
mistyped folios, track the portal's business-day counter, ask the client only
for what the portal does not have, remind once, and draft an answer whose every
claim about the entity's records quotes the client verbatim. It never files:
the human officer approves and files.

Input is one event at a time; output is a list of actions. State is kept per
context (one A2A contextId = one run), so the same process can serve many runs.

Events (JSON):
  {"type": "portal_snapshot", "today": "2026-11-05", "ok": true,
   "complaints": [{"folio", "received", "deadline", "claimant",
                   "says_is_client", "phone_called", "phone_caller", "reason"}]}
  {"type": "portal_snapshot", "today": ..., "ok": false, "error": "..."}
  {"type": "client_message", "today": ..., "id": "m-1", "text": "..."}
  {"type": "tick", "today": ...}
  {"type": "officer_approval", "folio": ...}

Actions (JSON), each with "action" and, when it must be delivered, "to":
  case_opened, case_linked, deadline, request_evidence (to client),
  draft_ready (to officer), blocked (to officer), duplicate_ignored, noted.
The agent never emits an action that files with the regulator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import calendar, evidence, folios, interpret

REMIND_AFTER_BUSINESS_DAYS = 2

# Fixed catalogue of what may be asked of the client. The text sent is never
# model-written; only validated folio numbers and phone digits are inserted.
ASK = {
    "analysis": "your analysis of the complaint (who made the collection contact and what happened)",
    "caller_number": "whether number {caller} (the one that called the claimant) is yours",
    "records": "whether the claimant, their phone or e-mail appear in your system",
}


@dataclass
class Case:
    folio: str
    complaint: dict[str, Any]
    chat_aliases: set[str] = field(default_factory=set)
    client_texts: list[str] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)
    asked_on: str | None = None
    reminded: bool = False
    draft: dict[str, Any] | None = None
    approved: bool = False
    blocked_reason: str | None = None
    reading: dict[str, Any] | None = None     # interpreter output for client_texts[:reading_n]
    reading_n: int = 0


class Agent:
    def __init__(self, interpreter: interpret.Interpreter | None = None) -> None:
        self.interpreter = interpreter or interpret.default()
        self.cases: dict[str, Case] = {}
        self.seen_messages: set[str] = set()
        self.unlinked: list[dict[str, Any]] = []  # client messages naming unknown folios

    # -- entry point -----------------------------------------------------

    def handle(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        kind = event.get("type")
        fn = getattr(self, "_on_" + str(kind), None)
        if fn is None:
            return [{"action": "blocked", "to": "officer",
                     "reason": f"unknown event type {kind!r}",
                     "owner": "integration", "next_action": "fix the adapter"}]
        return fn(event)

    # -- portal ----------------------------------------------------------

    def _on_portal_snapshot(self, ev):
        if not ev.get("ok", False):
            # Fail closed: never turn an unreadable portal into "nothing open".
            return [{"action": "blocked", "to": "officer",
                     "reason": "regulator portal could not be read: " + str(ev.get("error", "unknown")),
                     "owner": "compliance officer",
                     "next_action": "check the REDECO portal manually today; the agent retries next run",
                     "open_cases_known": sorted(self.cases)}]
        today = calendar.parse(ev["today"])
        out = []
        for c in ev.get("complaints", []):
            f = c["folio"]
            if f in self.cases:
                out.append({"action": "duplicate_ignored", "folio": f})
                continue
            self.cases[f] = Case(f, c)
            out.append({"action": "case_opened", "folio": f})
        out += self._relink()
        for case in self.cases.values():
            out.append(self._deadline(case, today))
            out += self._maybe_ask(case, ev["today"])
        return out

    def _deadline(self, case: Case, today) -> dict[str, Any]:
        c = case.complaint
        day, total = calendar.portal_day(calendar.parse(c["received"]),
                                         calendar.parse(c["deadline"]), today)
        return {"action": "deadline", "folio": case.folio, "day": day, "of": total,
                "label": f"{day} de {total}", "deadline": c["deadline"]}

    # -- client chat -----------------------------------------------------

    def _on_client_message(self, ev):
        mid = str(ev.get("id", ""))
        if mid and mid in self.seen_messages:
            return [{"action": "duplicate_ignored", "message": mid}]
        self.seen_messages.add(mid)
        named = folios.find_folios(ev.get("text", ""))
        if not named:
            return [{"action": "noted", "message": mid, "reason": "no folio in message"}]
        out = []
        for chat_folio in named:
            target = folios.link(chat_folio, set(self.cases))
            if target is None:
                self.unlinked.append({"folio": chat_folio, "text": ev["text"]})
                out.append({"action": "noted", "message": mid, "folio": chat_folio,
                            "reason": "not (yet) in the portal; kept for linking"})
                continue
            case = self.cases[target]
            if chat_folio != target and chat_folio not in case.chat_aliases:
                case.chat_aliases.add(chat_folio)
                out.append({"action": "case_linked", "chat_folio": chat_folio, "portal_folio": target})
            case.client_texts.append(ev["text"])
            out += self._maybe_draft(case)
        return out

    def _relink(self):
        out, keep = [], []
        for m in self.unlinked:
            target = folios.link(m["folio"], set(self.cases))
            if target is None:
                keep.append(m)
                continue
            case = self.cases[target]
            if m["folio"] != target:
                case.chat_aliases.add(m["folio"])
                out.append({"action": "case_linked", "chat_folio": m["folio"], "portal_folio": target})
            case.client_texts.append(m["text"])
        self.unlinked = keep
        return out

    # -- evidence requests -------------------------------------------------

    def _read(self, case: Case) -> dict[str, Any]:
        """What the client said, read by the interpreter (LLM or rules). Re-read only when a
        new message arrives. A reading whose quote is not verbatim in the messages is
        discarded: the conclusion is kept only if the client's own words support it."""
        if case.reading is None or case.reading_n != len(case.client_texts):
            r = self.interpreter(case.complaint, list(case.client_texts))  # may raise InterpreterError
            r = dict(r, unverified=[])
            for status_key, quote_key, open_values in (("client_status", "client_quote", ("unclear", "conflict")),
                                                       ("caller", "caller_quote", ("unclear", None))):
                if r.get(status_key) in open_values:
                    continue
                if evidence.unsupported([{"claim": status_key, "quote": r.get(quote_key) or ""}], case.client_texts):
                    r["unverified"].append(status_key)
                    r[status_key] = "unclear"
            case.reading, case.reading_n = r, len(case.client_texts)
        return case.reading

    def _missing(self, case: Case) -> list[str]:
        if not case.client_texts:
            need = ["analysis", "records"]
            return need + (["caller_number"] if case.complaint.get("phone_caller") else [])
        r = self._read(case)
        need = []
        if r["client_status"] == "unclear":
            need.append("records")
        if case.complaint.get("phone_caller") and r["caller"] == "unclear":
            need.append("caller_number")
        return need

    def _ask_text(self, case: Case, keys: list[str], reminder: bool) -> str:
        caller = "".join(ch for ch in str(case.complaint.get("phone_caller", "")) if ch.isdigit())[:10]
        items = "\n".join("- " + ASK[k].format(caller=caller or "in the complaint") for k in keys)
        head = "Reminder: to" if reminder else "To"
        return (f"{head} finish the answer to complaint {case.folio.split('/')[-1]} "
                f"(due {case.complaint['deadline']}) we only need:\n{items}")

    def _maybe_ask(self, case: Case, today: str):
        if case.draft:
            return []
        try:
            need = self._missing(case)
        except interpret.InterpreterError as exc:
            return self._interpreter_down(case, exc)
        if not need:
            return []
        new = [k for k in need if k not in case.asked]
        if new:
            case.asked += new
            case.asked_on = today
            return [{"action": "request_evidence", "to": "client", "folio": case.folio,
                     "items": new, "text": self._ask_text(case, new, False)}]
        if (not case.reminded and case.asked_on and
                calendar.business_days_between(calendar.parse(case.asked_on),
                                               calendar.parse(today)) >= REMIND_AFTER_BUSINESS_DAYS):
            case.reminded = True
            return [{"action": "request_evidence", "to": "client", "folio": case.folio,
                     "items": need, "reminder": True, "text": self._ask_text(case, need, True)}]
        return []

    def _on_tick(self, ev):
        today = calendar.parse(ev["today"])
        out = []
        for case in self.cases.values():
            if case.approved:
                continue
            out.append(self._deadline(case, today))
            out += self._maybe_ask(case, ev["today"])
        return out

    # -- drafting ---------------------------------------------------------

    def _block(self, case: Case, key: str, reason: str, next_action: str):
        if case.blocked_reason == key:  # one alert per problem, not one per message
            return []
        case.blocked_reason = key
        return [{"action": "blocked", "to": "officer", "folio": case.folio, "reason": reason,
                 "owner": "compliance officer", "next_action": next_action}]

    def _interpreter_down(self, case: Case, exc: Exception):
        # Fail closed: no reading means no draft and no new questions to the client.
        return self._block(case, "interpreter", f"could not read the client's messages: {exc}",
                           "retry next run; meanwhile the officer reads the chat")

    def _maybe_draft(self, case: Case):
        try:
            r = self._read(case)
            missing = self._missing(case)
        except interpret.InterpreterError as exc:
            return self._interpreter_down(case, exc)
        out = []
        if r["unverified"]:
            out += self._block(case, "unverified:" + ",".join(r["unverified"]),
                               "the interpreter's quote for " + ", ".join(r["unverified"])
                               + " is not in the client's messages; reading discarded",
                               "the agent asks the client again; officer may read the chat")
        status = r["client_status"]
        if case.draft and not case.approved:
            same = (status == ("client" if case.draft["template"] == "A" else "not_client")
                    and r["caller"] != "ours")
            if same:
                return out
            # A later message changed what the client says: the old draft no longer holds.
            out.append({"action": "draft_withdrawn", "to": "officer", "folio": case.folio,
                        "reason": "a later client message changed the facts the draft relied on"})
            case.draft = None
        elif case.draft:
            return out
        if status == "conflict":
            return out + self._block(case, "conflict", "the client's messages contradict each other on "
                                     "whether the claimant is a client", "confirm with the client before any draft")
        if missing:
            return out
        c = case.complaint
        is_client = status == "client"
        citations = [{"claim": "claimant is a client" if is_client else "claimant is not a client",
                      "quote": r["client_quote"]}]
        body = ("SÍ se identificó a la persona que presenta la queja, ya que SÍ es cliente de esta Entidad."
                if is_client else
                "NO se identificó a la persona que presenta la queja, ya que NO es cliente de esta Entidad.")
        if c.get("phone_caller"):
            if r["caller"] == "ours":
                return out + self._block(case, "caller_ours", f"the client says the caller number "
                                         f"{c['phone_caller']} is theirs; the standard templates do not apply",
                                         "officer writes this answer")
            # Only cite what the draft states (v0.1.1), and state what it cites (v0.1.2).
            citations.append({"claim": "caller number does not belong to the entity", "quote": r["caller_quote"]})
            body += f" El número {c['phone_caller']} desde el que se realizó la llamada no pertenece a esta Entidad."
        text = (f"Referencia: folio {case.folio}\n\nC. {c.get('claimant', '').upper()}.\n\n"
                f"En atención a la queja presentada a través del REDECO con folio {case.folio}, {body} "
                f"En ese sentido, esta Entidad emite su respuesta Desfavorable al Usuario, toda vez que no se "
                f"acredita la conducta señalada ({c.get('reason', '')}).")
        bad = evidence.unsupported(citations, case.client_texts)
        if bad:  # grounding failed: do not hand the officer an ungrounded draft
            return out + [{"action": "blocked", "to": "officer", "folio": case.folio,
                           "reason": "draft claims without a client quote: " + "; ".join(b["claim"] for b in bad),
                           "owner": "agent", "next_action": "ask the client"}]
        case.blocked_reason = None
        case.draft = {"folio": case.folio, "sense": "Desfavorable al Usuario",
                      "template": "A" if is_client else "B", "text": text, "citations": citations,
                      "interpreted_by": r["by"]}
        return out + [{"action": "draft_ready", "to": "officer", **case.draft}]

    def _on_officer_approval(self, ev):
        case = self.cases.get(ev.get("folio", ""))
        if case is None or case.draft is None:
            return [{"action": "blocked", "to": "officer", "reason": "approval for a folio with no draft",
                     "owner": "compliance officer", "next_action": "check the folio"}]
        case.approved = True
        # The agent records the approval; filing stays with the officer.
        return [{"action": "noted", "folio": case.folio, "reason": "approved; officer files with the regulator"}]
