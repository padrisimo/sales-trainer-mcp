from fastapi.testclient import TestClient

from sales_trainer.web.app import app

client = TestClient(app)


def test_root_returns_placeholder_html() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Sales Trainer" in response.text


def test_root_echoes_session_token() -> None:
    response = client.get("/?session=token-123")
    assert response.status_code == 200
    assert "token-123" in response.text
