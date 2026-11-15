# HW9 cold-start evidence

- `task.md` — the only instructions the fresh calling agent received (plus the doc URLs and service URL).
- `criteria.md` — success criteria, written before run 1.
- `logged_server.py` — runs the service with every request/response logged.
- `run1.jsonl`, `run2.jsonl` — server-side logs (v0.1.1, then v0.1.2).
- `run1/`, `run2/` — what each calling agent delivered (officer brief, client outbox, integration notes, its own call log).
- `verify.py` → `verify_run1.txt`, `verify_run2.txt` — criteria C1–C6 checked on the logs.

Repeat:

```bash
pip install -e '.[dev]'
python evidence/hw9/logged_server.py 8951 /tmp/run.jsonl &      # service + log
# give a fresh agent session evidence/hw9/task.md (change the output folder), no other context
python evidence/hw9/verify.py /tmp/run.jsonl
```

## Real-model check (v0.2.x)

`real_model_check.py` replays the cold-start messages plus harder phrasings
through the LLM and through the offline rules (expected outcomes written first).
Run in GitHub Actions with the production bot's OpenAI key (gpt-5-mini):

- `real_model_run1.txt` — v0.2.1: LLM 11/12, rules 8/12. The model read
  "si es cliente, lo buscamos…" as "is a client".
- `real_model_run2.txt` — v0.2.2 (prompt spells out conditions): LLM 12/12,
  rules 8/12. Includes the model's reading and quote for every case.

- `before_v011.txt` — the same 12 cases on v0.1.1 (the code in cold-start run 1): 2/12.

Note: the fix in 0.2.2 was made after seeing case 5 fail, so run 2 is not an
unseen test for that case.
