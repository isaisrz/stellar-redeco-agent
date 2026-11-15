# Integration notes: Stellar REDECO agent service

Service: http://127.0.0.1:8951. The agent card reports version 0.1.1. Every call used contextId `sofom-redeco-2026-11-13-run1`. Raw requests and responses are logged in `work/calls.jsonl`, and the event payloads are in `work/e1.json` to `work/e4.json`.

## Calls, in order
0. `GET /.well-known/agent-card.json` returned 200 (discovery; name stellar-redeco-agent, v0.1.1).
1. `message/send` id `m1-portal-20261112`, `portal_snapshot` with today=2026-11-12, both complaints, and `phone_caller` omitted for 91102. Result: completed, with case_opened ×2, deadline 91058 "3 de 10", request_evidence 91058 [analysis, records, caller_number], deadline 91102 "2 de 10", and request_evidence 91102 [analysis, records].
2. `message/send` id `m2-msg-0940`, `client_message` with today=2026-11-13 and id `ops-chat-2026-11-13-0940`, carrying the 09:40 text verbatim (folio typed 91085). Result: completed, with case_linked 91085→91058 and draft_ready 91058 (template B, "Desfavorable al Usuario", 2 citations).
3. `message/send` id `m3-msg-1015`, `client_message` with today=2026-11-13 and id `ops-chat-2026-11-13-1015`, carrying the 10:15 text verbatim. Result: completed, with draft_ready 91102 **template A** (wrong; see below).
4. `message/send` id `m4-tick-20261113`, `tick` with today=2026-11-13. Result: completed, with deadline 91058 "4 de 10" and 91102 "3 de 10". No reminders.

I sent no `officer_approval`; that is the officer's act.

## Defects found
- **Negation not handled (serious).** For 91102, the client wrote "el señor no es cliente nuestro, no aparece en el sistema." The service produced template A ("SÍ es cliente de esta Entidad") and added "El número 3322220002 que señaló corresponde a sus datos de contacto", which nobody stated. INTERFACE §8 says client status is recognized when a sentence "contains 'es cliente'". That rule matches "no es cliente" as well, and the docs never say how the service decides between is and is-not.
- **The grounding check is weaker than the docs suggest.** README: "A draft is released only if every citation appears in a message the client actually sent." That held: the quotes were verbatim. But the check does not test whether the draft's claims follow from those quotes. The 91102 draft cited a quote that says the opposite of the draft. The 91058 draft also says "El teléfono y correo que señaló no se encuentran en la base de datos", which no message says.
- **Citation not used in the text.** In 91058 the caller-number quote is cited, but the draft never states the caller-number fact.
- **No `blocked`** was raised for the 91102 contradiction or for the folio typo.

## Unclear or wrong in the docs
- The port is 8950 in README and INTERFACE, but the running instance was 8951, as I was told. Not a defect, just a difference.
- "Folio one digit away" (INTERFACE §5) suggests a single-digit substitution. The service also linked a **two-digit transposition** (91085→91058). README says "one edit away", so transpositions apparently count as one edit. The link was probably right here, but the docs should say so.
- The portal_snapshot example in §5 contains `//` comments, so it is not valid JSON as written. I stripped them.
- The §6 table lists `deadline` with `label` and `deadline` only, but the actual reply also contains `day` and `of`. That is consistent with the §9 example.
- `request_evidence.text` is in English, while the docs talk about Spanish-speaking clients and recognize client statements only in Spanish. The docs tell callers to deliver it unchanged. I did not, because it was partly answered and in English; see client_outbox.md.
- §5 does not say whether the counter follows the portal or the service's own calendar. The returned counters only reach "10 de 10" on the portal deadlines if Mon 16/11/2026 is a business day. The docs say only that "2026 CONDUSEF non-working days are loaded" and do not list them.
- `officer_approval` has no `today` field in the docs, unlike every other event.
- The docs say nothing about which values `sense` can take, or who chooses it.

## What I had to guess
- **Event dates.** The portal snapshot used today=2026-11-12, the day it was read. The chat messages and the tick used 2026-11-13. I had no portal reading for 2026-11-13, and I did not fabricate one.
- **Folio 91102 caller.** I treated "(vacío)" as "omit `phone_caller`", following the doc comment.
- **Message ids.** I made them up from the chat timestamps.
- **Sending text unchanged.** I sent the client messages exactly as written, including the wrong folio. I did not correct 91085 myself, because citations must quote the client verbatim and correcting it would have meant guessing on the client's behalf.
- I assumed the server keeps state in memory across my four calls, which it did (one contextId).
