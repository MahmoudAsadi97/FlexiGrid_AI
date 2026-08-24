"""Shared test infrastructure: an in-process mock LLM server."""

from __future__ import annotations

import os
import threading
import time

os.environ.setdefault("FLEXIGRID_EMBEDDINGS", "tfidf")  # deterministic tests

MOCK_PORT = 11436
MOCK_BASE_URL = f"http://127.0.0.1:{MOCK_PORT}/v1"

_server = None
_thread: threading.Thread | None = None


def start_mock_llm() -> str:
    """Start the OpenAI-compatible mock server once per test process."""
    global _server, _thread
    if _thread is not None:
        return MOCK_BASE_URL
    import uvicorn

    from flexigrid.dev_mock_llm import app

    config = uvicorn.Config(app, host="127.0.0.1", port=MOCK_PORT,
                            log_level="error")
    _server = uvicorn.Server(config)
    _thread = threading.Thread(target=_server.run, daemon=True)
    _thread.start()
    deadline = time.time() + 10
    while not _server.started and time.time() < deadline:
        time.sleep(0.05)
    if not _server.started:
        raise RuntimeError("mock LLM server failed to start")
    return MOCK_BASE_URL


def use_mock_llm() -> None:
    """Point the process at the mock server and reset cached clients."""
    from flexigrid.llm import reset_llm

    start_mock_llm()
    os.environ["FLEXIGRID_LLM_BASE_URL"] = MOCK_BASE_URL
    os.environ["FLEXIGRID_LLM_MODEL"] = "mock-planner-1"
    reset_llm()


def use_no_llm() -> None:
    """Point the process at a dead port so llm.available() is False."""
    from flexigrid.llm import reset_llm

    os.environ["FLEXIGRID_LLM_BASE_URL"] = "http://127.0.0.1:9"  # discard port
    os.environ["FLEXIGRID_LLM_MODEL"] = "nothing"
    reset_llm()
