import os
import subprocess
import time
import urllib.error
import urllib.request

import pytest
from playwright.sync_api import sync_playwright

PORT = 8125
BASE_URL = f"http://127.0.0.1:{PORT}"


def _wait_for_server(timeout_seconds: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = urllib.request.urlopen(f"{BASE_URL}/debug/tts", timeout=2)
            try:
                if response.status == 200:
                    return
            finally:
                response.close()
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    raise RuntimeError("web server did not become ready in time")


@pytest.mark.e2e
def test_debug_tts_page_speaks_and_moves_the_mouth() -> None:
    env = {**os.environ, "SALES_TRAINER_TTS": "mock"}
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
                ]
            )
            page = browser.new_page()

            def on_console(message) -> None:
                if message.type == "error":
                    errors.append(message.text)

            page.on("console", on_console)
            page.on("pageerror", lambda error: errors.append(str(error)))

            page.goto(f"{BASE_URL}/debug/tts")
            page.wait_for_function("window.ttsDebug && window.ttsDebug.ready === true")

            page.click("#speak")
            page.wait_for_function("window.ttsDebug.speaking === true")

            seen = set()
            for _ in range(20):
                seen.add(page.evaluate("window.ttsDebug.activeViseme"))
                page.wait_for_timeout(80)

            page.wait_for_function("window.ttsDebug.speaking === false", timeout=10000)

            assert page.evaluate("window.ttsDebug.timelineLength") >= 5
            assert len(seen) >= 2, f"the mouth never changed viseme: {seen}"
            assert errors == []
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
