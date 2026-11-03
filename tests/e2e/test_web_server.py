import subprocess
import time
import urllib.request

import pytest

PORT = 8123
BASE_URL = f"http://127.0.0.1:{PORT}"


def _wait_for_server(timeout_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = urllib.request.urlopen(f"{BASE_URL}/?session=smoke", timeout=2)
            try:
                if response.status == 200:
                    return
            finally:
                response.close()
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("web server did not become ready in time")


@pytest.mark.e2e
def test_web_server_serves_placeholder() -> None:
    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "sales_trainer.web.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_server()
        response = urllib.request.urlopen(f"{BASE_URL}/?session=smoke-token", timeout=10)
        try:
            assert response.status == 200
            assert "text/html" in response.headers["Content-Type"]
            assert "smoke-token" in response.read().decode()
        finally:
            response.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
