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
