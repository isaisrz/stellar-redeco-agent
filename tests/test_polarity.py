"""Regression tests for v0.1.2: found by the HW9 cold-start run, where a fresh
calling agent sent "el señor no es cliente nuestro" and v0.1.1 drafted
"SÍ es cliente de esta Entidad"."""
import pytest

from stellar_redeco import evidence
from stellar_redeco.agent import Agent


@pytest.mark.parametrize("text,expected", [
    ("el señor no es cliente nuestro, no aparece en el sistema.", "not_client"),   # the run-1 message
    ("No es cliente.", "not_client"),
    ("La quejosa no es nuestra cliente", "not_client"),
    ("Los datos no corresponden a ningún cliente registrado en nuestro sistema.", "not_client"),
    ("No lo tenemos registrado en el sistema", "not_client"),
    ("No aparece en nuestra base", "not_client"),
    ("Sí es cliente de la entidad.", "client"),
    ("Persona Sintetica Dos es cliente de la entidad.", "client"),
    ("Es nuestro cliente desde 2024", "client"),
    ("Lo estamos revisando", None),          # not a statement: never guessed
    ("Creo que tal vez sí", None),
    # "si" without an accent (v0.1.3): "yes" typed without the accent ...
    ("si es cliente.", "client"),
    ("Si es cliente de la entidad.", "client"),
    ("si, es cliente", "client"),
    (__import__("unicodedata").normalize("NFD", "Sí es cliente"), "client"),   # iPhone accents
    # ... versus "if / whether": hedges and questions are not answers
    ("Si es cliente, lo buscamos en el sistema.", None),
    ("Si es cliente hay que revisar su expediente", None),
    ("No sé si es cliente", None),
    ("no se si es cliente", None),
    ("No sabemos si es cliente, lo revisamos", None),
    ("Vamos a confirmar si es cliente", None),
    ("¿Es cliente?", None),
    ("es cliente?", None),
    ("No sé si no es cliente", None),
])

def test_client_status_polarity(text, expected):
    assert evidence.client_status(text) == expected


def _run(messages, caller="3398765432"):
    a = Agent()
    c = {"folio": "2026/REDECO/91102", "received": "10/11/2026", "deadline": "24/11/2026",
         "claimant": "Pedro Muestra Sintetico", "says_is_client": "No", "phone_called": "3322220002",
         "reason": "Amenazar, ofender o intimidar"}
    if caller:
        c["phone_caller"] = caller
    a.handle({"type": "portal_snapshot", "today": "2026-11-12", "ok": True, "complaints": [c]})
    out = []
    for i, t in enumerate(messages):
        out += a.handle({"type": "client_message", "today": "2026-11-13", "id": f"m{i}", "text": t})
    return out


def test_run1_message_now_gets_template_b():
    out = _run(["Sobre la 2026/REDECO/91102: el señor no es cliente nuestro, no aparece en el sistema."], caller=None)
    d = [x for x in out if x["action"] == "draft_ready"][0]
    assert d["template"] == "B" and "NO es cliente" in d["text"] and "SÍ" not in d["text"]
    assert "corresponde a sus datos" not in d["text"]          # unsupported v0.1.1 sentence is gone


def test_template_b_states_what_it_cites_and_nothing_more():
    out = _run(["2026/REDECO/91102: Los datos no corresponden a ningún cliente registrado. "
                "El número 3398765432 no pertenece a la entidad."])
    d = [x for x in out if x["action"] == "draft_ready"][0]
    assert "3398765432 desde el que se realizó la llamada no pertenece" in d["text"]
    assert "correo" not in d["text"]                           # v0.1.1 claimed phone AND e-mail checked
    assert len(d["citations"]) == 2


def test_unrecognized_statement_asks_instead_of_drafting():
    out = _run(["2026/REDECO/91102: lo estamos revisando con el despacho."], caller=None)
    assert not any(x["action"] == "draft_ready" for x in out)


def test_contradiction_after_a_draft_withdraws_it_and_blocks_once():
    out = _run(["2026/REDECO/91102: sí es cliente.", "2026/REDECO/91102: perdón, no es cliente.",
                "2026/REDECO/91102: confirmamos que no es cliente."], caller=None)
    kinds = [x["action"] for x in out]
    assert kinds.index("draft_ready") < kinds.index("draft_withdrawn") < kinds.index("blocked")
    assert kinds.count("draft_ready") == 1                       # no new draft while they contradict
    blocked = [x for x in out if x["action"] == "blocked"]
    assert len(blocked) == 1 and blocked[0]["to"] == "officer"


def test_caller_number_owned_by_entity_goes_to_officer():
    out = _run(["2026/REDECO/91102: no es cliente. El número 3398765432 sí es nuestro, de cobranza."])
    assert not any(x["action"] == "draft_ready" for x in out)
    assert [x for x in out if x["action"] == "blocked"][0]["owner"] == "compliance officer"


@pytest.mark.parametrize("text,expected", [
    ("El número 3398765432 no pertenece a la entidad.", "not_ours"),
    ("El número 3398765432 sí es nuestro.", "ours"),
    ("No sé si el número 3398765432 es nuestro", None),
    ("Vamos a revisar si el 3398765432 pertenece a algún despacho", None),
    ("¿El 3398765432 es nuestro?", None),
])
def test_caller_ownership_hedges(text, expected):
    assert evidence.caller_ownership(text) == expected


def test_hedged_reply_keeps_asking_instead_of_drafting():
    out = _run(["2026/REDECO/91102: no sé si es cliente, lo estamos revisando."], caller=None)
    assert not any(x["action"] == "draft_ready" for x in out)
