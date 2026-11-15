# stellar-redeco-agent

The deterministic core of **Stellar Compliance AI**'s REDECO agent, published as
an [A2A](https://a2a-protocol.org) endpoint so other systems (for example
[Nanda Town](https://github.com/projnanda/nandatown)) can test it.

Stellar PLD runs compliance for Mexican non-bank lenders (SOFOMs). When a
consumer files a complaint with CONDUSEF's REDECO system, the lender has
**10 business days** to answer. Our agent does the officer's preparation work:
reads the regulator portal, opens one case per complaint, links folios the
client typed wrong, tracks the portal's business-day counter ("6 de 10"), asks
the client only for what the portal does not have, reminds once, and drafts an
answer whose every claim quotes the client verbatim. **It never files.** The
human compliance officer approves and files.

This repository contains only the generic, deterministic logic and
**synthetic data**. The production deployment (Telegram, Google Sheets, the
real portal reader, LLM drafting) lives in a private repository and never
ships client data.

## Interface

Calling-agent documentation (inputs, outputs, limits, example): [docs/INTERFACE.md](docs/INTERFACE.md).

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
stellar-redeco-agent serve --port 8950
```

- Agent card: `GET http://127.0.0.1:8950/.well-known/agent-card.json`
- `POST /` JSON-RPC `message/send` with one text part holding a JSON event.
  The reply is a completed task whose text artifact is `{"actions": [...]}`.
  Use one `contextId` per run (state is kept per context).

Events: `portal_snapshot` (`ok: false` when the portal could not be read),
`client_message`, `tick`, `officer_approval`. Actions: `case_opened`,
`case_linked`, `deadline`, `request_evidence` (to the client, fixed
catalogue only), `draft_ready` (to the officer), `blocked` (to the officer,
with reason, owner and next action), `duplicate_ignored`, `noted`.

## Design rules

- **Fail closed.** An unreadable portal, an unknown event or a calendar year
  without published non-working days produces `blocked`, never "nothing open".
- **Deterministic rules decide**, not a model: business days, folio linking
  (one edit away from exactly one portal folio, otherwise abstain), what to ask.
- **Grounded drafts.** A draft is released only if every citation appears in
  a message the client actually sent (accent- and punctuation-insensitive), the
  statement's polarity matches the draft, and the draft says nothing it does not cite.
- **Human gate.** No action files with the regulator.

## Versions

- `0.1.2` — fixes a defect found by a cold-start test (HW9): a fresh calling
  agent sent "el señor no es cliente nuestro" and v0.1.1 drafted "SÍ es
  cliente", because it matched the substring "es cliente". Statements are now
  classified by polarity; unrecognized statements are asked again; contradictions
  block (and withdraw a draft); drafts state only what they cite. Interface docs
  now list the field mapping and non-working days.
- `0.1.1` — fixes a defect found by the Nanda Town `redeco_compliance`
  scenario: v0.1.0 always cited the "number that made the collection call",
  so a complaint without one could never be drafted.
- `0.1.0` — first public release.

MIT AI Studio (MAS.665), Fall 2026 — team Stellar Compliance AI.
