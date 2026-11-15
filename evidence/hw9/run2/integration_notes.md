# Integration notes: Stellar REDECO agent (run2, 2026-11-13)

Service: http://127.0.0.1:8951. The agent card reports version 0.1.2.
All JSON-RPC calls used `message/send` with contextId `opk2-redeco-2026-11-13-run2`.
Client script: `call.py`. The raw request and response for every JSON-RPC call is logged in `calls.log`; the agent-card GET (call 1) was made with curl and is not in that file.

## Calls, in order
1. `GET /.well-known/agent-card.json` → 200. Name stellar-redeco-agent, version 0.1.2, url :8951.
2. `portal_snapshot` (today 2026-11-12, ok true, folios 91058 and 91102; `phone_caller` left out for 91102 because the portal field was empty) → completed. Returned:
   - `case_opened` ×2;
   - `deadline` 91058 "3 de 10" (due 23/11) and 91102 "2 de 10" (due 24/11);
   - `request_evidence` 91058 [analysis, records, caller_number] and 91102 [analysis, records].
3. `client_message` id `ops-2026-11-13-0940` (today 2026-11-13, the 09:40 text verbatim, folio typed 91085) → completed. Returned:
   - `case_linked` 91085→91058;
   - `draft_ready` 91058, template B, 2 citations.
4. `client_message` id `ops-2026-11-13-1015` (today 2026-11-13, the 10:15 text verbatim) → completed. Returned `draft_ready` 91102, template B, 1 citation.
5. `tick` (today 2026-11-13) → completed. Returned `deadline` 91058 "4 de 10" and 91102 "3 de 10".

I sent no `officer_approval`; that is the human officer's decision. I made no other calls.

## Unclear or wrong in the docs
- **Port.** The README and INTERFACE use 8950. The running instance is on 8951, which the task stated. The agent card's `url` is correct.
- **Counters are not refreshed by client messages.** A `client_message` with a new `today` returns no `deadline` action. I needed a separate `tick` to get today's counter. The docs present `tick` as "nothing new" and do not say this.
- **Evidence asked versus evidence required.** `request_evidence` asks for `analysis` and `records`. §8, however, releases a draft on just the client-status statement plus, where the complaint has one, the caller-number statement. Both drafts came out with no analysis. The docs do not say that `analysis` is optional.
- **Third-party collection.** Template B treats "not a client" as enough for "Gestiones de cobro a terceros" and for complaints that have no caller number. A third-party collection complaint concerns a non-client by definition, so that statement does not address the conduct. The docs do not flag this. I raised it with the officer instead.
- **Draft narrows a quote.** The quote "no pertenece a la entidad ni a nuestros despachos de cobranza" became "no pertenece a esta Entidad" in the draft. This is consistent with "says nothing it does not cite", but it silently drops the collection-agency part.
- **Language.** `request_evidence.text` is English in this build, so it cannot be "delivered unchanged" to a Spanish-speaking client as §6 instructs. I did not forward it.
- **Typo linking.** The folio typo was linked automatically and silently. A `case_linked` action is returned, but no `blocked` asks a human to confirm. The docs do not say whether the calling agent should ask for confirmation. I asked the client and flagged it for the officer.

## What I guessed
- **Snapshot date.** I gave the portal snapshot `today: 2026-11-12`, because that is when the screen was copied. I did not invent a snapshot for 13/11.
- **Field formats.** I passed the portal values as shown: `"No"` for `says_is_client`, dd/mm/yyyy dates, and the claimant name with its accent.
- **Message ids.** The docs only require unique `id`s. I built them from the chat timestamps. `messageId` and the JSON-RPC `id` are random UUIDs.
- **Message text.** I sent the two chat messages verbatim, including the mistyped folio, as separate `client_message` events in the order they were sent.
- **Draft validity.** I assumed the drafts stay valid without re-sending the portal snapshot today. The service gave no warning about stale portal data.
