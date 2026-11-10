import pytest

from sales_trainer import mcp_server
from sales_trainer.web import sessions


def test_build_url_uses_local_host_and_token() -> None:
    url = mcp_server.build_url(port=8765, token="token-123")
    assert url == "http://127.0.0.1:8765/?session=token-123"


def test_start_returns_url_and_session_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "_ensure_server", lambda: None)
    monkeypatch.setattr(mcp_server.webbrowser, "open", lambda url: True)

    result = mcp_server.start(level=1, product_brief=None, language="es")

    assert set(result) == {"url", "session_id"}
    assert result["url"] == f"http://127.0.0.1:8765/?session={result['session_id']}"
    assert result["session_id"]


def test_status_returns_not_running_when_server_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "_server", None)
    monkeypatch.setattr(mcp_server, "_thread", None)
    assert mcp_server.status() == {"running": False}


def test_stop_is_safe_when_server_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "_server", None)
    monkeypatch.setattr(mcp_server, "_thread", None)
    assert mcp_server.stop() == {"running": False}


def test_start_registers_the_session_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "_ensure_server", lambda: None)
    monkeypatch.setattr(mcp_server.webbrowser, "open", lambda url: True)

    result = mcp_server.start(level=1, product_brief=None, language="es")

    assert sessions.is_known(result["session_id"]) is True
