"""Web chat UI for the Olist sales analytics agent.

Standard library only. Imports the agent as a library (no agent files are
modified) and serves a static chat page plus a small JSON API:

  GET  /            the chat page (files under ./static)
  GET  /api/info    model name and server URL, for the header badge
  GET  /api/health  whether the model server is reachable, for the status card
  POST /api/chat    {session, message} -> the agent's Reply as JSON
  POST /api/reset   {session} -> clears that conversation

Run from the repository root with the project's virtualenv:
  python ui/server.py
"""
import dataclasses
import json
import mimetypes
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
# The agent lives in the repository root, one level up from ui/.
AGENT_DIR = Path(os.getenv("AGENT_DIR", HERE.parent)).resolve()
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
MAX_BODY = 64 * 1024

# The agent opens "data/olist.duckdb" relative to the working directory.
sys.path.insert(0, str(AGENT_DIR))
os.chdir(AGENT_DIR)

import llm  # noqa: E402
from agent import Agent  # noqa: E402

_sessions: dict[str, tuple[Agent, threading.Lock]] = {}
_sessions_lock = threading.Lock()


def get_session(session_id: str) -> tuple[Agent, threading.Lock]:
    with _sessions_lock:
        if session_id not in _sessions:
            _sessions[session_id] = (Agent(), threading.Lock())
        return _sessions[session_id]


def friendly_error(exc: Exception) -> str:
    name = type(exc).__name__
    if "Connection" in name or "Timeout" in name:
        return (f"Can't reach the local model at {llm.BASE_URL}. "
                f"Is Ollama running with the model '{llm.MODEL}'?")
    if "NotFound" in name:
        return f"The model server doesn't know the model '{llm.MODEL}'. Check `ollama list`."
    return f"The agent failed: {name}: {exc}"


class Handler(BaseHTTPRequestHandler):
    server_version = "SalesAgentUI/1.0"

    # ---- helpers -------------------------------------------------------
    def _send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: dict):
        self._send(status, json.dumps(data).encode(), "application/json")

    def _read_json(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return None
        try:
            data = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    # ---- routes --------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/info":
            return self._json(200, {"model": llm.MODEL, "base_url": llm.BASE_URL})
        if path == "/api/health":
            # Is the model server reachable and serving the model? (for the status card)
            try:
                llm.check_server()
                return self._json(200, {"ok": True})
            except Exception as e:  # noqa: BLE001 - report any failure as "not ready"
                return self._json(200, {"ok": False, "error": str(e)})
        if path == "/":
            path = "/index.html"

        target = (STATIC_DIR / path.lstrip("/")).resolve()
        if not target.is_relative_to(STATIC_DIR) or not target.is_file():
            return self._json(404, {"error": "Not found"})
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/javascript":
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        data = self._read_json()
        session = data.get("session") if data else None
        if not isinstance(session, str) or not session.strip():
            return self._json(400, {"error": "Missing session id."})

        if path == "/api/reset":
            agent, lock = get_session(session)
            with lock:
                agent.reset()
            return self._json(200, {"ok": True})

        if path == "/api/chat":
            message = data.get("message")
            if not isinstance(message, str) or not message.strip():
                return self._json(400, {"error": "Empty message."})
            agent, lock = get_session(session)
            start = time.time()
            with lock:  # one turn at a time per conversation
                try:
                    reply = agent.ask(message.strip())
                except Exception as e:  # noqa: BLE001 - report any agent failure to the UI
                    traceback.print_exc()
                    return self._json(502, {"error": friendly_error(e)})
            return self._json(200, {**dataclasses.asdict(reply),
                                    "elapsed": round(time.time() - start, 1)})

        self._json(404, {"error": "Not found"})

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")


def main():
    if not (AGENT_DIR / "agent.py").exists():
        raise SystemExit(f"Agent not found in {AGENT_DIR}. Set AGENT_DIR to the agent directory.")
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Agent:  {AGENT_DIR}")
    print(f"Model:  {llm.MODEL} at {llm.BASE_URL}")
    print(f"Open    http://{HOST}:{PORT}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
