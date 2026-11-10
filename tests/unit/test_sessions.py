import uuid

from fastapi.testclient import TestClient

from sales_trainer.web import sessions
from sales_trainer.web.app import app

client = TestClient(app)


def test_an_unknown_token_is_not_known() -> None:
    assert sessions.is_known(f"unknown-{uuid.uuid4()}") is False


def test_a_registered_token_is_known() -> None:
    token = f"known-{uuid.uuid4()}"
    sessions.register(token)
    assert sessions.is_known(token) is True


def test_an_empty_token_is_never_known() -> None:
    assert sessions.is_known("") is False


def test_loading_a_page_registers_the_session_token() -> None:
    token = f"page-{uuid.uuid4()}"
    response = client.get(f"/debug/tts?session={token}")
    assert response.status_code == 200
    assert sessions.is_known(token) is True
