"""The REDECO compliance agent as a deterministic state machine.

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

from . import calendar, evidence, folios

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


class Agent:
    def __init__(self) -> None:
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

    def _missing(self, case: Case) -> list[str]:
        src = case.client_texts
        need = []
        if not src:
            need.append("analysis")
        if not self._statement_records(case):
            need.append("records")
        if case.complaint.get("phone_caller") and not self._statement_caller(case):
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
        need = self._missing(case)
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

    def _statement_records(self, case: Case) -> str | None:
        s = case.client_texts
        return (evidence.find_sentence(s, "no corresponden", "cliente")
                or evidence.find_sentence(s, "es cliente"))

    def _statement_caller(self, case: Case) -> str | None:
        caller = str(case.complaint.get("phone_caller", ""))
        return evidence.find_sentence(case.client_texts, caller) if caller else None

    def _maybe_draft(self, case: Case):
        if case.draft or self._missing(case):
            return []
        c = case.complaint
        records = self._statement_records(case)
        caller = self._statement_caller(case)
        is_client = "es cliente" in evidence.norm(records) and "no corresponden" not in evidence.norm(records)
        citations = [{"claim": "client status per entity records", "quote": records},
                     {"claim": "number that made the collection contact", "quote": caller}]
        if is_client:
            body = (f"SÍ se identificó a la persona que presenta la queja, ya que SÍ es cliente de esta Entidad. "
                    f"El número {c.get('phone_called', '')} que señaló corresponde a sus datos de contacto.")
        else:
            body = (f"NO se identificó a la persona que presenta la queja, ya que NO es cliente de esta Entidad. "
                    f"El teléfono y correo que señaló no se encuentran en la base de datos de esta Entidad.")
        text = (f"Referencia: folio {case.folio}\n\nC. {c.get('claimant', '').upper()}.\n\n"
                f"En atención a la queja presentada a través del REDECO con folio {case.folio}, {body} "
                f"En ese sentido, esta Entidad emite su respuesta Desfavorable al Usuario, toda vez que no se "
                f"acredita la conducta señalada ({c.get('reason', '')}).")
        bad = evidence.unsupported(citations, case.client_texts)
        if bad:  # grounding failed: do not hand the officer an ungrounded draft
            return [{"action": "blocked", "to": "officer", "folio": case.folio,
                     "reason": "draft claims without a client quote: " + "; ".join(b["claim"] for b in bad),
                     "owner": "agent", "next_action": "ask the client"}]
        case.draft = {"folio": case.folio, "sense": "Desfavorable al Usuario",
                      "template": "A" if is_client else "B", "text": text, "citations": citations}
        return [{"action": "draft_ready", "to": "officer", **case.draft}]

    def _on_officer_approval(self, ev):
        case = self.cases.get(ev.get("folio", ""))
        if case is None or case.draft is None:
            return [{"action": "blocked", "to": "officer", "reason": "approval for a folio with no draft",
                     "owner": "compliance officer", "next_action": "check the folio"}]
        case.approved = True
        # The agent records the approval; filing stays with the officer.
        return [{"action": "noted", "folio": case.folio, "reason": "approved; officer files with the regulator"}]
