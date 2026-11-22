import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


def test_api_serves_real_http_with_isolated_storage(tmp_path):
    if sys.platform == "win32":
        pytest.skip("Passing a listening socket to Uvicorn requires POSIX")

    env = {
        **os.environ,
        "SQLITE_DB_PATH": str(tmp_path / "metadata.db"),
        "CHROMA_PERSIST_DIR": str(tmp_path / "chroma"),
        "BM25_INDEX_PATH": str(tmp_path / "bm25.pkl"),
        "CHROMA_HOST": "",
    }
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "src.api.main:app", "--fd", str(listener.fileno())],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            pass_fds=(listener.fileno(),),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=1, trust_env=False) as client:
                deadline = time.monotonic() + 30
                while True:
                    assert process.poll() is None, "Uvicorn exited before becoming ready"
                    try:
                        live = client.get("/api/live")
                        if live.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if time.monotonic() >= deadline:
                        pytest.fail("Uvicorn did not become ready within 30 seconds")
                    time.sleep(0.1)

                assert live.json() == {"status": "alive"}
                schema = client.get("/openapi.json")
                assert schema.status_code == 200
                assert "/api/query" in schema.json()["paths"]
                sources = client.get("/api/sources")
                assert sources.status_code == 200
                assert sources.json() == []
                assert client.post("/api/ingest", json={}).status_code == 422
                metrics = client.get("/metrics")
                assert metrics.status_code == 200
                assert "http" in metrics.text
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
