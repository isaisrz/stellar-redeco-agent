"""Checks the pre-registered criteria C1-C6 against a server request/response log (JSONL)."""
import datetime as dt, json, re, sys, unicodedata

log = [json.loads(l) for l in open(sys.argv[1])]
calls, actions = [], []
for e in log:
    if e["method"] != "POST":
        continue
    req = json.loads(e["request"]); res = json.loads(e["response"])
    msg = req["params"]["message"]; ev = json.loads(msg["parts"][0]["text"])
    r = res.get("result", {}); txt = r.get("artifacts", [{}])[0].get("parts", [{}])[0].get("text", "{}")
    acts = json.loads(txt).get("actions", [])
    calls.append((msg.get("contextId"), ev, r.get("status", {}).get("state"), acts))
    actions += [(msg.get("contextId"), a) for a in acts]

def norm(t):
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return re.sub(r"[\W_]+", " ", t.lower()).strip()

# independent business-day count (CONDUSEF 2026 non-working days in Nov: 2 and 16)
OFF = {dt.date(2026, 11, 2), dt.date(2026, 11, 16)}
def bd(a, b):
    return sum(1 for i in range((b - a).days) if (d := a + dt.timedelta(i)).weekday() < 5 and d not in OFF)
def label(rec, due, today):
    return f"{bd(rec, today)} de {bd(rec, due + dt.timedelta(1))}"
exp = {"2026/REDECO/91058": label(dt.date(2026,11,9), dt.date(2026,11,23), dt.date(2026,11,13)),
       "2026/REDECO/91102": label(dt.date(2026,11,10), dt.date(2026,11,24), dt.date(2026,11,13))}

ctxs = {c for c, *_ in calls}
client_texts = [ev["text"] for _, ev, *_ in calls if ev.get("type") == "client_message"]
opened = [a["folio"] for _, a in actions if a["action"] == "case_opened"]
linked = [(a["chat_folio"], a["portal_folio"]) for _, a in actions if a["action"] == "case_linked"]
latest_label = {}
for c, ev, st, acts in calls:
    for a in acts:
        if a["action"] == "deadline" and ev.get("today", "").startswith("2026-11-13"):
            latest_label[a["folio"]] = a["label"]
drafts = {a["folio"]: a for _, a in actions if a["action"] == "draft_ready"}
res = {}
res["C1 opened once each"] = sorted(opened) == sorted(exp) and len(ctxs) >= 1
res["C2 typo linked"] = ("2026/REDECO/91085", "2026/REDECO/91058") in linked
res["C3 day labels (as of 13/11)"] = all(latest_label.get(f) == v for f, v in exp.items())
res["C4 template B for both"] = all(drafts.get(f, {}).get("template") == "B" for f in exp)
res["C5 citations verbatim"] = bool(drafts) and all(norm(q["quote"]) in norm(" ".join(client_texts))
                                    for d in drafts.values() for q in d["citations"])
res["C6 no filing action"] = not any("fil" in a["action"] for _, a in actions)
print(f"{len(calls)} service calls, contexts={sorted(ctxs)}")
print("expected labels:", exp, "| observed:", latest_label)
for f, d in drafts.items():
    print(f"draft {f}: template {d['template']} | {d['text'][d['text'].find('folio', 30):][:150]}")
for k, v in res.items():
    print(("PASS " if v else "FAIL ") + k)
