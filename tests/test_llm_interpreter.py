"""v0.2.0: an LLM reads the client's messages; code verifies its quotes.

The model is stubbed here (no API key in CI): each test scripts what the model
answers and checks what the agent does with it. The real model was not called.
"""
import json

import pytest

from stellar_redeco import interpret
from stellar_redeco.agent import Agent

C1 = {"folio": "2026/REDECO/91058", "received": "09/11/2026", "deadline": "23/11/2026",
      "claimant": "Laura Ejemplo Ficticia", "says_is_client": "No", "phone_called": "3311110001",
      "phone_caller": "3398765432", "reason": "Gestiones de cobro a terceros"}
C2 = {"folio": "2026/REDECO/91102", "received": "10/11/2026", "deadline": "24/11/2026",
      "claimant": "Pedro Muestra Sintetico", "says_is_client": "No", "phone_called": "3322220002",
      "reason": "Amenazar, ofender o intimidar"}
MSG1 = ("Buen día. Revisamos la queja 2026/REDECO/91085. Los datos de la quejosa no corresponden a ningún "
        "cliente registrado en nuestro sistema. El número 3398765432 no pertenece a la entidad ni a nuestros "
        "despachos de cobranza.")
MSG2 = "Sobre la 2026/REDECO/91102: el señor no es cliente nuestro, no aparece en el sistema."


class Model:
    """Stub of the Messages API: returns scripted answers and records the prompts."""
    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def __call__(self, prompt, model, key):
        self.prompts.append(prompt)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a if isinstance(a, str) else json.dumps(a)


def agent(model, complaints=(C2,)):
    a = Agent(interpret.llm(model="test-model", api_key="x", post=model))
    a.handle({"type": "portal_snapshot", "today": "2026-11-12", "ok": True, "complaints": list(complaints)})
    return a


def msg(a, text, i="m1", today="2026-11-13"):
    return a.handle({"type": "client_message", "today": today, "id": i, "text": text})


def kinds(out):
    return [x["action"] for x in out]


def test_run1_negation_read_by_the_model():
    m = Model({"client_status": "not_client", "client_quote": "el señor no es cliente nuestro", "caller": None})
    out = msg(agent(m), MSG2)
    d = [x for x in out if x["action"] == "draft_ready"][0]
    assert d["template"] == "B" and d["interpreted_by"] == "llm:test-model"
    assert "2026/REDECO/91102" in m.prompts[0] and "no es cliente nuestro" in m.prompts[0]


def test_both_run1_complaints_with_caller_number():
    m = Model({"client_status": "not_client",
               "client_quote": "Los datos de la quejosa no corresponden a ningún cliente registrado en nuestro sistema.",
               "caller": "not_ours",
               "caller_quote": "El número 3398765432 no pertenece a la entidad ni a nuestros despachos de cobranza."})
    out = msg(agent(m, (C1, C2)), MSG1)
    assert "case_linked" in kinds(out)                     # folio typo still linked by code
    d = [x for x in out if x["action"] == "draft_ready"][0]
    assert d["folio"] == "2026/REDECO/91058" and len(d["citations"]) == 2
    assert "3398765432 desde el que se realizó la llamada no pertenece" in d["text"]


def test_quote_not_in_messages_is_discarded():
    # The model paraphrases (or invents) the evidence: its reading is not trusted.
    m = Model({"client_status": "not_client", "client_quote": "El cliente no está registrado con nosotros",
               "caller": None})
    out = msg(agent(m), MSG2)
    assert "draft_ready" not in kinds(out)
    b = [x for x in out if x["action"] == "blocked"][0]
    assert "not in the client's messages" in b["reason"]


def test_unclear_means_ask_again_not_draft():
    m = Model({"client_status": "unclear", "client_quote": None, "caller": None})
    a = agent(m)
    out = msg(a, "2026/REDECO/91102: no sé si es cliente, lo revisamos.")
    assert "draft_ready" not in kinds(out)
    out = a.handle({"type": "tick", "today": "2026-11-17"})
    asks = [x for x in out if x["action"] == "request_evidence"]
    assert asks and "records" in asks[0]["items"]
    assert len(m.prompts) == 1                              # re-read only when a new message arrives


def test_model_down_fails_closed():
    m = Model(RuntimeError("timeout"), RuntimeError("timeout"))
    a = agent(m)
    out = msg(a, MSG2)
    assert "draft_ready" not in kinds(out)
    assert [x for x in out if x["action"] == "blocked"][0]["to"] == "officer"
    out = a.handle({"type": "tick", "today": "2026-11-17"})
    assert "request_evidence" not in kinds(out)            # no questions to the client on a failed reading


def test_model_answer_that_is_not_json_fails_closed():
    out = msg(agent(Model("Claro, el señor no es cliente.")), MSG2)
    assert "draft_ready" not in kinds(out) and "blocked" in kinds(out)


def test_correction_after_a_draft_withdraws_and_redrafts():
    m = Model({"client_status": "client", "client_quote": "sí es cliente", "caller": None},
              {"client_status": "not_client", "client_quote": "perdón, me equivoqué, no es cliente", "caller": None})
    a = agent(m)
    first = msg(a, "2026/REDECO/91102: sí es cliente.", "m1")
    assert [x["template"] for x in first if x["action"] == "draft_ready"] == ["A"]
    out = msg(a, "2026/REDECO/91102: perdón, me equivoqué, no es cliente.", "m2")
    assert kinds(out).index("draft_withdrawn") < kinds(out).index("draft_ready")
    assert [x["template"] for x in out if x["action"] == "draft_ready"] == ["B"]


def test_caller_number_owned_by_entity_goes_to_officer():
    m = Model({"client_status": "not_client", "client_quote": "no es cliente",
               "caller": "ours", "caller_quote": "el 3398765432 sí es de nuestro despacho"})
    out = msg(agent(m, (C1,)), "2026/REDECO/91058: no es cliente, pero el 3398765432 sí es de nuestro despacho.")
    assert "draft_ready" not in kinds(out)
    assert "templates do not apply" in [x for x in out if x["action"] == "blocked"][0]["reason"]


def test_default_interpreter(monkeypatch):
    monkeypatch.delenv("STELLAR_INTERPRETER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert interpret.default() is interpret.rules            # offline: phrase rules
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    assert interpret.default() is not interpret.rules        # key present: the model reads
    assert interpret.provider() == ("openai", "gpt-5-mini")
    monkeypatch.setenv("STELLAR_INTERPRETER", "rules")
    assert interpret.default() is interpret.rules
