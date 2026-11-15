# stellar-redeco-agent — interface for calling agents

This page is written for an agent (or its builder) that has never seen this
project. It covers what the service does, how to reach it, the exact inputs
and outputs, the limits, setup, and one worked example.

## 1. What it offers

A Mexican lender (SOFOM) that receives a consumer complaint through CONDUSEF's
**REDECO** portal must answer within **10 business days**. This service does
the compliance officer's preparation work for each complaint:

| You send | It returns |
|---|---|
| What the portal shows (complaints, dates) | One case per complaint, the portal's day counter ("4 de 10"), duplicate detection |
| What the lender (the "client") wrote in chat | Links the message to the right complaint, even with a one-digit folio typo |
| Nothing new for a while (`tick`) | One reminder to the client if evidence is still missing |
| Enough client evidence | A **draft answer** for the human officer, with each fact backed by a verbatim quote of the client |

It **never files** with the regulator and never writes free text to the
client: messages to the client come from a fixed catalogue. A human
compliance officer reviews, approves and files.

**Who does what.** An LLM reads the client's messages and decides what they
say (is the claimant a client? is the caller number theirs?), quoting the exact
sentence. Code does what has one right answer: business-day counters, folio
links, checking that every quote is really in the client's messages, and the
hard limit that nothing is ever filed. Without an API key the service reads
messages with offline phrase rules instead (deterministic; see §8).

## 2. Access

- Transport: [A2A](https://a2a-protocol.org) over HTTP, JSON-RPC 2.0.
- Default base URL when you run it locally: `http://127.0.0.1:8950`.
- No authentication (it holds only synthetic data and runs on localhost).
  Do not expose it on a public interface.
- Discovery: `GET /.well-known/agent-card.json`.

## 3. Setup

```bash
git clone https://github.com/isaisrz/stellar-redeco-agent
cd stellar-redeco-agent
python3 -m venv .venv && source .venv/bin/activate   # Python 3.11+
pip install -e '.[dev]'
pytest -q                                           # all tests should pass
stellar-redeco-agent serve --port 8950              # Ctrl+C to stop
```

To let the LLM read the client's messages, set before `serve`:

```bash
export OPENAI_API_KEY=...       # model gpt-5-mini by default
# or: export ANTHROPIC_API_KEY=...   # model claude-sonnet-5-5 by default
export STELLAR_LLM_MODEL=...    # optional override
# no key: offline phrase rules
```

The agent card's `interpreter` field shows which one is active.

## 4. Calling it

Every call is a JSON-RPC `message/send` whose message has **one text part
containing one JSON event** (the event is a JSON string inside the text part).

```json
{"jsonrpc": "2.0", "id": 1, "method": "message/send",
 "params": {"message": {"role": "user", "messageId": "any-unique-id",
   "contextId": "run-42",
   "parts": [{"kind": "text", "text": "<one JSON event, as a string>"}]}}}
```

- **`contextId` is the case file.** State (open cases, messages seen, what was
  asked) is kept per `contextId`. Use the same one for every event of a run;
  a new `contextId` starts from zero.
- Send events **in the order they happened**, each with its own `today`.
- The reply is a JSON-RPC result holding a task. If `result.status.state` is
  `completed`, `result.artifacts[0].parts[0].text` is a JSON string
  `{"actions": [...]}`. If it is `failed`, the same place holds
  `{"error": "..."}` (malformed input; nothing was guessed).

## 5. Input events

Dates: `today` is ISO (`2026-11-13`). Portal dates may be `dd/mm/yyyy` (as the
portal shows them) or ISO.

### `portal_snapshot` — what the REDECO portal shows today

```json
{"type": "portal_snapshot", "today": "2026-11-12", "ok": true,
 "complaints": [{"folio": "2026/REDECO/91058", "received": "09/11/2026",
   "deadline": "23/11/2026", "claimant": "Nombre Apellido", "says_is_client": "No",
   "phone_called": "3300000001", "phone_caller": "3300000009",
   "reason": "Gestiones de cobro a terceros"}]}
```

| field | portal column | required | notes |
|---|---|---|---|
| `folio` | Folio | yes | `YYYY/REDECO/NNNNN` |
| `received` | Fecha de recepción | yes | |
| `deadline` | Fecha límite de respuesta | yes | |
| `claimant` | Nombre del usuario | no | used in the draft heading |
| `says_is_client` | ¿Dice ser cliente? | no | what the claimant declared; informational |
| `phone_called` | Teléfono al que llamaron | no | |
| `phone_caller` | Número que realizó la llamada | no | **omit** when the portal field is empty; when present, the client must say whether it is theirs |
| `reason` | Causa | no | quoted at the end of the draft |

If the portal could not be read, send `{"type": "portal_snapshot", "today": ..., "ok": false, "error": "why"}`.
The service answers `blocked` (never "nothing open").

### `client_message` — a message the lender sent

```json
{"type": "client_message", "today": "2026-11-13", "id": "msg-7",
 "text": "Sobre la 2026/REDECO/91058: ..."}
```

- `id` must be unique per message; a repeated `id` is ignored as a duplicate.
- The text must contain the folio in the form `YYYY/REDECO/NNNNN` (or with
  `-`). A message with no folio is only `noted`.
- A folio one edit away (one digit changed, two adjacent digits swapped, or one
  digit added or missing) from exactly one open complaint is linked to it
  (`case_linked`). If it matches none (or two), it is kept and linked when the
  complaint appears in a later `portal_snapshot`.
- The service recognizes the client's statement **in Spanish** (see §8).

### `tick` — time passed, nothing new

`{"type": "tick", "today": "2026-11-17"}` — refreshes counters and sends at most
one reminder per case, after 2 business days without an answer.

### `officer_approval`

`{"type": "officer_approval", "folio": "2026/REDECO/91058"}` (no `today` needed) — records that the
human officer approved the draft. Filing remains the officer's job.

## 6. Output actions

Each action has `action`; actions meant for someone have `to`.

| action | to | meaning / key fields |
|---|---|---|
| `case_opened` | — | new complaint, `folio` |
| `duplicate_ignored` | — | same complaint or same message `id` seen again |
| `case_linked` | — | `chat_folio` (as the client typed it) → `portal_folio` |
| `deadline` | — | `day`, `of`, `label` e.g. `"4 de 10"` (business days elapsed, receipt day included and today excluded, of business days up to the deadline — the portal's counter), `deadline` |
| `request_evidence` | `client` | `items` (catalogue keys `analysis`, `records`, `caller_number`), `text` ready to send (English in this public build; production sends the Spanish catalogue), `reminder: true` on the follow-up |
| `draft_ready` | `officer` | `text` (Spanish answer), `template` (`A` claimant is a client, `B` is not), `sense`, `citations` [{claim, quote}], `interpreted_by` (`llm:<model>` or `rules`) |
| `draft_withdrawn` | `officer` | a later client message changed the facts an unapproved draft relied on; a new draft follows when the facts are clear |
| `blocked` | `officer` | something needs a human: `reason`, `owner`, `next_action`. Sent once per problem; a contradiction after a draft also **withdraws** that draft |
| `noted` | — | recorded, nothing to do (`reason`) |

A calling agent should: deliver `request_evidence.text` to the client unchanged,
put `draft_ready` in front of the human officer with its `citations`, and treat
any `blocked` as a task for the named `owner`.

## 7. Limits and permissions

- Never files with CONDUSEF and has no action that could.
- Calendar: only 2026 CONDUSEF non-working days are loaded (weekends plus 1–2 Jan,
  2 Feb, 16 Mar, 2–3 Apr, 1 and 5 May, 20–31 Jul, 16 Sep, 2 and 16 Nov,
  17–31 Dec). Any date outside 2026 fails closed (`failed` task or `blocked`).
  Example: received 09/11/2026, due 23/11/2026 is exactly 10 business days
  because 16/11 is non-working.
- State lives in memory; restarting the server forgets every `contextId`.
- Synthetic data only. Do not send real personal data. In LLM mode the client's
  messages and the complaint are sent to the model provider (OpenAI or Anthropic).
- If the LLM cannot be reached or answers in an unexpected format, the case is
  `blocked` (no draft and no new questions to the client) until the next read.
- Drafts cover the two collection-complaint answers Stellar uses most (claimant
  is / is not a client). Other complaint types are out of scope.

## 8. What evidence produces a draft

The client's messages about a complaint are read (by the LLM, or by the
offline rules) to answer two questions, each with the exact sentence it rests on:

1. **Is the claimant a client?** `not_client` → template B; `client` →
   template A; `unclear` (no statement, a question, doubt, a condition such as
   "no sé si es cliente" or "si es cliente, lo buscamos") → the agent asks the
   client again; `conflict` (messages contradict each other and no later
   message settles it) → no draft, `blocked` to the officer. A clear later
   correction ("perdón, sí es cliente") replaces the earlier statement and an
   unapproved draft is withdrawn (`draft_withdrawn`) and redone.
2. **If the complaint has a `phone_caller`: is that number theirs?** `not_ours`
   → stated in the draft; `ours` → the standard templates do not apply,
   `blocked` for the officer; `unclear` → asked again.

**The reading is not trusted blindly.** Each quote must appear verbatim in the
client's messages (accents, case and punctuation ignored). A reading whose quote
is not there is discarded and reported as `blocked`; the agent asks again. The
draft states only what those quotes say, and the officer reviews every draft.

Offline phrase rules (no API key) recognize, e.g., "no es cliente", "no
corresponden a ningún cliente", "no aparece", "sí es cliente"/"si es cliente.",
and treat questions, doubt and conditions as unclear. They are a fallback:
phrasings they do not know are asked again.

## 9. Worked example

Request (one portal snapshot, new `contextId`):

```bash
curl -s http://127.0.0.1:8950/ -H 'content-type: application/json' -d '{
 "jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{
  "role":"user","messageId":"m1","contextId":"demo-1","parts":[{"kind":"text",
  "text":"{\"type\":\"portal_snapshot\",\"today\":\"2026-11-05\",\"ok\":true,\"complaints\":[{\"folio\":\"2026/REDECO/90824\",\"received\":\"27/10/2026\",\"deadline\":\"10/11/2026\",\"claimant\":\"Persona Sintetica Uno\",\"says_is_client\":\"No\",\"phone_called\":\"5500000001\",\"phone_caller\":\"5500000009\",\"reason\":\"Amenazar, ofender o intimidar\"}]}"}]}}}'
```

Decoded `{"actions": ...}` from the reply:

```json
[{"action": "case_opened", "folio": "2026/REDECO/90824"},
 {"action": "deadline", "folio": "2026/REDECO/90824", "day": 6, "of": 10,
  "label": "6 de 10", "deadline": "10/11/2026"},
 {"action": "request_evidence", "to": "client", "folio": "2026/REDECO/90824",
  "items": ["analysis", "records", "caller_number"],
  "text": "To finish the answer to complaint 90824 (due 10/11/2026) we only need:\n- your analysis of the complaint (who made the collection contact and what happened)\n- whether the claimant, their phone or e-mail appear in your system\n- whether number 5500000009 (the one that called the claimant) is yours"}]
```

Next, send the client's reply as a `client_message` in the same `contextId`;
once the evidence in §8 is present, the reply contains `draft_ready`.
