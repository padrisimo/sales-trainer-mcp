from fastapi.testclient import TestClient

from sales_trainer.web.app import app

client = TestClient(app)


def test_debug_visemes_returns_html() -> None:
    response = client.get("/debug/visemes")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "/static/js/debug.js" in response.text


def test_debug_visemes_includes_canvas_and_panel() -> None:
    response = client.get("/debug/visemes")
    assert 'id="avatar"' in response.text
    assert 'id="panel"' in response.text
