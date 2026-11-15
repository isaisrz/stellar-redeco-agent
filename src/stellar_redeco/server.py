"""A2A endpoint for the REDECO agent.

GET  /.well-known/agent-card.json   AgentCard
POST /  JSON-RPC 2.0 "message/send": one text part holding a JSON event.
        The reply is a completed task with one text artifact: {"actions": [...]}.
        Agent state is kept per contextId (send the same contextId for one run).

    stellar-redeco-agent serve --port 8950
"""
from __future__ import annotations

import argparse
import json
import uuid
from typing import Any

from fastapi import FastAPI, Request

from . import __version__, interpret
from .agent import Agent


def interpreter_name() -> str:
    f = interpret.default()
    return "rules" if f is interpret.rules else "llm:%s/%s" % interpret.provider()


def agent_card(base_url: str) -> dict[str, Any]:
    return {
        "name": "stellar-redeco-agent",
        "description": "Prepares answers to REDECO (CONDUSEF, Mexico) consumer complaints for a "
                       "human compliance officer: portal intake, folio-typo linking, business-day "
                       "deadlines, evidence requests, grounded drafts. Never files. Synthetic data.",
        "url": base_url,
        "version": __version__,
        "capabilities": {"streaming": False, "pushNotifications": False},
        "interpreter": interpreter_name(),
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [{
            "id": "redeco-compliance",
            "name": "REDECO complaint preparation",
            "description": "Send one JSON event {type: portal_snapshot|client_message|tick|"
                           "officer_approval, ...}; receive JSON {actions: [...]}. Keep one "
                           "contextId per run.",
            "tags": ["compliance", "redeco", "condusef", "human-in-the-loop"],
        }],
    }


def build_app(base_url: str = "http://127.0.0.1:8950") -> FastAPI:
    app = FastAPI(title="stellar-redeco-agent", version=__version__)
    agents: dict[str, Agent] = {}
    tasks: dict[str, dict[str, Any]] = {}

    @app.get("/.well-known/agent-card.json")
    @app.get("/.well-known/agent.json")
    def card():
        return agent_card(base_url)

    @app.post("/")
    async def rpc(request: Request):
        msg = await request.json()
        rid = msg.get("id")
        if msg.get("method") == "tasks/get":
            task = tasks.get(msg.get("params", {}).get("id", ""))
            if task is None:
                return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32001, "message": "task not found"}}
            return {"jsonrpc": "2.0", "id": rid, "result": task}
        if msg.get("method") != "message/send":
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32601, "message": f"method {msg.get('method')!r} not found"}}
        m = msg.get("params", {}).get("message", {})
        text = next((p.get("text", "") for p in m.get("parts", []) if p.get("kind") == "text"), "")
        task_id = "task-" + uuid.uuid4().hex[:12]
        ctx = m.get("contextId") or "default"
        try:
            event = json.loads(text)
            if not isinstance(event, dict):
                raise ValueError("event must be a JSON object")
            ctx = m.get("contextId") or str(event.get("context") or "default")
            actions = agents.setdefault(ctx, Agent()).handle(event)
            state, payload = "completed", {"actions": actions}
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
            # Malformed input is reported, never guessed at.
            state, payload = "failed", {"error": f"{type(exc).__name__}: {exc}"}
        task = {"id": task_id, "contextId": ctx, "kind": "task", "status": {"state": state},
                "artifacts": [{"artifactId": "a-1", "name": "actions" if state == "completed" else "error",
                               "parts": [{"kind": "text", "text": json.dumps(payload, ensure_ascii=False)}]}]}
        tasks[task_id] = task
        return {"jsonrpc": "2.0", "id": rid, "result": task}

    return app


def main() -> None:
    ap = argparse.ArgumentParser(prog="stellar-redeco-agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the A2A endpoint")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8950)
    a = ap.parse_args()
    import uvicorn
    uvicorn.run(build_app(f"http://{a.host}:{a.port}"), host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
