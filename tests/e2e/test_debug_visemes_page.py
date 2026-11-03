import subprocess
import time
import urllib.error
import urllib.request

import pytest
from playwright.sync_api import sync_playwright

PORT = 8124
BASE_URL = f"http://127.0.0.1:{PORT}"
VISEMES = [
    "sil",
    "PP",
    "FF",
    "TH",
    "DD",
    "kk",
    "CH",
    "SS",
    "nn",
    "RR",
    "aa",
    "E",
    "I",
    "O",
    "U",
]


def _wait_for_server(timeout_seconds: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = urllib.request.urlopen(f"{BASE_URL}/debug/visemes", timeout=2)
            try:
                if response.status == 200:
                    return
            finally:
                response.close()
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    raise RuntimeError("web server did not become ready in time")


@pytest.mark.e2e
def test_debug_page_applies_each_viseme() -> None:
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
        errors: list[str] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
            )
            page = browser.new_page()

            def on_console(message) -> None:
                if message.type == "error":
                    errors.append(message.text)

            page.on("console", on_console)
            page.on("pageerror", lambda error: errors.append(str(error)))

            page.goto(f"{BASE_URL}/debug/visemes")
            page.wait_for_function("window.avatarDebug && window.avatarDebug.ready === true")

            buttons = page.locator("button[data-viseme]")
            assert buttons.count() == len(VISEMES) + 1

            for name in VISEMES:
                page.click(f'button[data-viseme="{name}"]')
                assert page.evaluate("window.avatarDebug.active") == name

            page.click('button[data-viseme="reset"]')
            assert page.evaluate("window.avatarDebug.active") == "sil"

            assert errors == []
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
