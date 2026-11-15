"""Runs stellar-redeco-agent with every JSON-RPC request/response appended to a JSONL log."""
import json, sys, time
import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from stellar_redeco.server import build_app

port, log = int(sys.argv[1]), sys.argv[2]
app = build_app(f"http://127.0.0.1:{port}")

class Log(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        body = await request.body()
        resp = await call_next(request)
        chunks = [c async for c in resp.body_iterator]
        out = b"".join(chunks)
        with open(log, "a") as f:
            f.write(json.dumps({"t": time.strftime("%H:%M:%S"), "method": request.method,
                                "path": request.url.path, "request": body.decode() or None,
                                "status": resp.status_code, "response": out.decode()}, ensure_ascii=False) + "\n")
        return Response(out, status_code=resp.status_code, headers=dict(resp.headers))

app.add_middleware(Log)
uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
