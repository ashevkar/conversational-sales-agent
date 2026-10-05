"""Unit tests for the friendly database and model-server errors. No model needed.

Run:  python tests/test_errors.py   (or: python -m pytest tests/)
"""
import socket
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb  # noqa: E402
from openai import OpenAI  # noqa: E402

import db  # noqa: E402
import llm  # noqa: E402


def _with_db_path(path, fn):
    saved = db.DB_PATH
    db.DB_PATH = str(path)
    try:
        return fn()
    finally:
        db.DB_PATH = saved


def _expect(exc_type, fn) -> str:
    try:
        fn()
    except exc_type as e:
        return str(e)
    raise AssertionError(f"expected {exc_type.__name__}")


def test_missing_database():
    msg = _with_db_path(Path(tempfile.mkdtemp()) / "none.duckdb",
                        lambda: _expect(db.DatabaseError, db.connect))
    assert "python load_data.py" in msg


def test_outdated_database():
    path = Path(tempfile.mkdtemp()) / "old.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE sales (x INT)")  # no order_facts / payments
    con.close()
    msg = _with_db_path(path, lambda: _expect(db.DatabaseError, db.connect))
    assert "order_facts" in msg and "python load_data.py" in msg


def _with_client(base_url, fn, timeout=2.0):
    saved = llm._client
    llm._client = OpenAI(base_url=base_url, api_key="local", timeout=timeout, max_retries=0)
    try:
        return fn()
    finally:
        llm._client = saved


def test_unreachable_server():
    url = "http://127.0.0.1:1/v1"  # nothing listens on port 1
    msg = _with_client(url, lambda: _expect(llm.LLMConnectionError,
                                            lambda: llm.chat([{"role": "user", "content": "hi"}])))
    assert "model server" in msg and "llama-server" in msg
    _with_client(url, lambda: _expect(llm.LLMConnectionError, llm.check_server))


def test_server_that_never_answers():
    # Accepts the connection but never replies, like a hung server.
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]
    held = []
    threading.Thread(target=lambda: held.append(sock.accept()), daemon=True).start()
    msg = _with_client(f"http://127.0.0.1:{port}/v1",
                       lambda: _expect(llm.LLMTimeoutError,
                                       lambda: llm.chat([{"role": "user", "content": "hi"}])),
                       timeout=1.0)
    sock.close()
    assert "did not answer" in msg and "LLM_TIMEOUT" in msg


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} tests passed")
