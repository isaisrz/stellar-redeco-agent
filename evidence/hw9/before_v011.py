"""Runs the 12 real-model-check cases on the v0.1.1 code (the version in cold-start run 1).
    git worktree add /tmp/v011 25ca893 && python evidence/hw9/before_v011.py /tmp/v011/src"""
import sys

sys.path.insert(0, __import__("os").path.dirname(__file__))
cases = __import__("real_model_check").CASES
for m in [k for k in sys.modules if k.startswith("stellar_redeco")]:
    del sys.modules[m]
sys.path.insert(0, sys.argv[1])
import stellar_redeco
from stellar_redeco.agent import Agent

print("version", stellar_redeco.__version__)
ok = 0
for name, c, msgs, exp in cases:
    a = Agent()
    a.handle({"type": "portal_snapshot", "today": "2026-11-12", "ok": True, "complaints": [c]})
    for i, m in enumerate(msgs):
        a.handle({"type": "client_message", "today": "2026-11-13", "id": f"m{i}", "text": m})
    d = a.cases[c["folio"]].draft
    got = d["template"] if d else "none"
    ok += got == exp
    print(f"{exp:<5} {got:<5} {'ok' if got == exp else 'X '} {name}")
print(f"\ncorrect: {ok}/{len(cases)}")
