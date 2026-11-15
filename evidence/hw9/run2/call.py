"""Send one event to the Stellar REDECO agent and append request/response to calls.log."""
import json, sys, urllib.request, uuid

URL = "http://127.0.0.1:8951/"
CTX = "opk2-redeco-2026-11-13-run2"

def send(event, ctx=CTX):
    body = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "message/send",
            "params": {"message": {"role": "user", "messageId": str(uuid.uuid4()),
                                   "contextId": ctx,
                                   "parts": [{"kind": "text", "text": json.dumps(event, ensure_ascii=False)}]}}}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"content-type": "application/json"})
    with urllib.request.urlopen(req) as r:
        resp = json.loads(r.read())
    res = resp.get("result", {})
    state = res.get("status", {}).get("state")
    try:
        payload = json.loads(res["artifacts"][0]["parts"][0]["text"])
    except Exception:
        payload = resp
    with open("/home/claude/hw9/run2/calls.log", "a") as f:
        f.write(json.dumps({"ctx": ctx, "event": event, "state": state, "payload": payload}, ensure_ascii=False) + "\n")
    print("STATE:", state)
    print(json.dumps(payload, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    send(json.loads(sys.argv[1]), *(sys.argv[2:3]))
