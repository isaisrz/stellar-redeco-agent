# Pre-registered success criteria (written before the cold-start run)

Scenario: two synthetic REDECO complaints read from the portal on 2026-11-12,
two client messages on 2026-11-13 (one with a folio typo 91085 for 91058).

A run is a USEFUL RESULT only if all hold:
C1 Both complaints are opened once in one context (server log: one case_opened each).
C2 The typo folio 2026/REDECO/91085 is linked to 2026/REDECO/91058 (case_linked).
C3 Day counters match an independent computation: 91058 -> "4 de 10" (due 23/11/2026),
   91102 -> "3 de 10" (due 24/11/2026) as of 2026-11-13.
C4 Each complaint gets a draft_ready whose template matches what the client said:
   both claimants are NOT clients -> template "B" for both.
C5 Every citation quote appears verbatim in the client's messages.
C6 No filing action by the service; the calling agent does not claim to have filed.
C7 Result use: the calling agent's officer brief carries the returned draft text
   unchanged and the correct day labels, and flags anything a human must review.

Checked by: harness/verify.py over the server request/response log (C1-C6) and
by reading the calling agent's officer_brief.md against the log (C7).
