import datetime as dt

from stellar_redeco import calendar, evidence, folios
from stellar_redeco.agent import Agent

NON_CLIENT = {"folio": "2026/REDECO/90824", "received": "27/10/2026", "deadline": "10/11/2026",
              "claimant": "Persona Sintetica Uno", "says_is_client": "No",
              "phone_called": "5500000001", "phone_caller": "5500000009",
              "reason": "Amenazar, ofender o intimidar"}


def test_portal_counter_matches_observed_portal():
    # Observed on the real portal on 2026-11-05: received 27/10, due 10/11 -> "6 de 10".
    assert calendar.portal_day(dt.date(2026, 10, 27), dt.date(2026, 11, 10), dt.date(2026, 11, 5)) == (6, 10)
    assert calendar.portal_day(dt.date(2026, 10, 28), dt.date(2026, 11, 11), dt.date(2026, 11, 5)) == (5, 10)


def test_calendar_fails_closed_outside_2026():
    try:
        calendar.is_business_day(dt.date(2027, 1, 4))
    except ValueError:
        return
    raise AssertionError("must refuse an unknown year")


def test_typo_linking_abstains_when_ambiguous():
    assert folios.link("2026/REDECO/90424", {"2026/REDECO/90824"}) == "2026/REDECO/90824"
    assert folios.link("2026/REDECO/90424", {"2026/REDECO/90824", "2026/REDECO/90414"}) is None


def test_accents_decomposed():
    import unicodedata
    src = [unicodedata.normalize("NFD", "no corresponden a ningún cliente")]
    assert evidence.unsupported([{"claim": "x", "quote": "No corresponden a ningún cliente"}], src) == []


def test_portal_down_blocks_instead_of_reporting_zero():
    a = Agent()
    out = a.handle({"type": "portal_snapshot", "today": "2026-11-05", "ok": False, "error": "timeout"})
    assert [x["action"] for x in out] == ["blocked"]
    assert out[0]["owner"] and out[0]["next_action"]


def test_end_to_end_non_client():
    a = Agent()
    a.handle({"type": "client_message", "today": "2026-10-27", "id": "m1",
              "text": "Nueva queja 2026/REDECO/90424, la revisamos."})
    out = a.handle({"type": "portal_snapshot", "today": "2026-10-28", "ok": True, "complaints": [NON_CLIENT]})
    kinds = [x["action"] for x in out]
    assert kinds.count("case_opened") == 1 and "case_linked" in kinds
    req = [x for x in out if x["action"] == "request_evidence"][0]
    assert set(req["items"]) == {"records", "caller_number"}
    again = a.handle({"type": "portal_snapshot", "today": "2026-10-28", "ok": True, "complaints": [NON_CLIENT]})
    assert "case_opened" not in [x["action"] for x in again]
    out = a.handle({"type": "client_message", "today": "2026-10-29", "id": "m2",
                    "text": "Sobre 2026/REDECO/90424: el número telefónico y el correo indicados en la queja "
                            "no corresponden a ningún cliente registrado en nuestro sistema. "
                            "El número 5500000009 no pertenece a la entidad."})
    draft = [x for x in out if x["action"] == "draft_ready"][0]
    assert draft["template"] == "B" and draft["to"] == "officer"
    assert not any(x["action"].startswith("file") for x in out)


def test_client_case_without_caller_number_gets_a_draft():
    # Regression for v0.1.0 (found by Nanda Town): a citation for a caller number
    # the complaint never mentioned blocked every such draft.
    a = Agent()
    c = {"folio": "2026/REDECO/91058", "received": "28/10/2026", "deadline": "11/11/2026",
         "claimant": "Persona Sintetica Dos", "says_is_client": "No", "phone_called": "8100000002",
         "reason": "Gestiones de cobro a terceros"}
    a.handle({"type": "portal_snapshot", "today": "2026-10-28", "ok": True, "complaints": [c]})
    out = a.handle({"type": "client_message", "today": "2026-10-28", "id": "m1",
                    "text": "Sobre la queja 2026/REDECO/91058: Persona Sintetica Dos es cliente de la entidad."})
    draft = [x for x in out if x["action"] == "draft_ready"][0]
    assert draft["template"] == "A" and len(draft["citations"]) == 1
