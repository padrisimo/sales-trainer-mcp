import base64
import io
import wave

import pytest
from fastapi.testclient import TestClient

from sales_trainer.web.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _use_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SALES_TRAINER_TTS", "mock")


def test_tts_returns_audio_and_visemes() -> None:
    response = client.post("/api/tts", json={"text": "Hola, soy Marta."})
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"audio_base64", "mime", "visemes"}
    assert payload["mime"] == "audio/wav"
    with wave.open(io.BytesIO(base64.b64decode(payload["audio_base64"])), "rb") as wav:
        assert wav.getnframes() > 0
    assert payload["visemes"]
    first = payload["visemes"][0]
    assert set(first) == {"t_ms", "viseme", "weight"}


def test_tts_rejects_empty_text() -> None:
    assert client.post("/api/tts", json={"text": ""}).status_code == 422


def test_tts_rejects_oversized_text() -> None:
    assert client.post("/api/tts", json={"text": "a" * 401}).status_code == 422


def test_tts_reports_unavailable_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SALES_TRAINER_TTS", "azure")
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    assert client.post("/api/tts", json={"text": "Hola."}).status_code == 503
