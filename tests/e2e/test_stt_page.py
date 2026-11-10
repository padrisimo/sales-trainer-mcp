import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

PORT = 8126
BASE_URL = f"http://127.0.0.1:{PORT}"
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "hola-marta-16k.wav"
TOKEN = "e2e-stt"


def _wait_for_server(timeout_seconds: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = urllib.request.urlopen(f"{BASE_URL}/debug/stt?session={TOKEN}", timeout=2)
            try:
                if response.status == 200:
                    return
            finally:
                response.close()
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    raise RuntimeError("web server did not become ready in time")


@pytest.mark.e2e
def test_debug_stt_page_transcribes_a_turn_from_the_fake_microphone() -> None:
    env = {**os.environ, "SALES_TRAINER_STT": "mock", "SALES_TRAINER_PORT": str(PORT)}
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
        env=env,
    )
    try:
        _wait_for_server()
        errors: list[str] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                args=[
                    "--use-angle=swiftshader",
                    "--enable-unsafe-swiftshader",
                    "--autoplay-policy=no-user-gesture-required",
                    "--use-fake-device-for-media-stream",
                    "--use-fake-ui-for-media-stream",
                    f"--use-file-for-fake-audio-capture={FIXTURE}",
                ]
            )
            page = browser.new_page()

            def on_console(message) -> None:
                if message.type == "error":
                    errors.append(message.text)

            page.on("console", on_console)
            page.on("pageerror", lambda error: errors.append(str(error)))

            page.goto(f"{BASE_URL}/debug/stt?session={TOKEN}")
            page.wait_for_function("window.sttDebug && window.sttDebug.ready === true")
            page.click("#start")
            page.wait_for_function("window.sttDebug.listening === true", timeout=15000)
            page.wait_for_function("window.sttDebug.turns.length > 0", timeout=30000)

            turns = page.evaluate("window.sttDebug.turns")
            assert turns[0]["text"]
            assert turns[0]["language"] == "es"
            assert turns[0]["words"]
            assert turns[0]["words"][0]["start_ms"] >= 0
            assert page.evaluate("window.sttDebug.lastError") is None
            assert errors == []
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
