import json, sys, urllib.request, uuid, datetime
CTX = "sofom-redeco-2026-11-13-run1"
LOG = "/home/claude/hw9/run1/work/calls.jsonl"
def send(event, mid):
    body = {"jsonrpc":"2.0","id":mid,"method":"message/send","params":{"message":{
        "role":"user","messageId":mid,"contextId":CTX,
        "parts":[{"kind":"text","text":json.dumps(event, ensure_ascii=False)}]}}}
    req = urllib.request.Request("http://127.0.0.1:8951/", data=json.dumps(body).encode(),
        headers={"content-type":"application/json"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode()
    resp = json.loads(raw)
    with open(LOG,"a") as f:
        f.write(json.dumps({"messageId":mid,"event":event,"response":resp}, ensure_ascii=False)+"\n")
    return resp
if __name__ == "__main__":
    ev = json.loads(open(sys.argv[1]).read()); mid = sys.argv[2]
    r = send(ev, mid)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    try:
        st = r["result"]["status"]["state"]; print("STATE:", st)
        print(json.dumps(json.loads(r["result"]["artifacts"][0]["parts"][0]["text"]), ensure_ascii=False, indent=1))
    except Exception as e: print("parse err", e)
