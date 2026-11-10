import uuid

import pytest
from fastapi.testclient import TestClient

from sales_trainer.web import sessions
from sales_trainer.web.app import app
from sales_trainer.web.routes import stt_ws

client = TestClient(app)
ORIGIN = "http://127.0.0.1:8765"
CHUNK = b"\x00\x00" * 512


@pytest.fixture
def session_token() -> str:
    token = f"ws-{uuid.uuid4()}"
    sessions.register(token)
    return token


class ScriptedVAD:
    def __init__(self, script: list[float]) -> None:
        self._script = list(script)

    def probability(self, chunk: bytes) -> float:
        return self._script.pop(0) if self._script else 0.0


def read_until(socket, kind: str) -> dict:
    while True:
        message = socket.receive_json()
        if message["type"] == kind:
            return message


def test_a_foreign_origin_is_rejected() -> None:
    token = f"ws-{uuid.uuid4()}"
    sessions.register(token)
    url = f"/ws/stt?session={token}"
    with client.websocket_connect(url, headers={"origin": "http://evil.example"}) as socket:
        payload = socket.receive_json()
    assert payload["type"] == "error"
    assert payload["code"] == "origin"


def test_a_missing_origin_is_rejected(session_token: str) -> None:
    url = f"/ws/stt?session={session_token}"
    with client.websocket_connect(url, headers={}) as socket:
        payload = socket.receive_json()
    assert payload["code"] == "origin"


def test_an_unknown_token_is_rejected() -> None:
    url = f"/ws/stt?session=nope-{uuid.uuid4()}"
    with client.websocket_connect(url, headers={"origin": ORIGIN}) as socket:
        payload = socket.receive_json()
    assert payload["type"] == "error"
    assert payload["code"] == "session"


def test_one_turn_produces_one_transcript_and_is_stored(monkeypatch: pytest.MonkeyPatch, session_token: str) -> None:
    monkeypatch.setenv("SALES_TRAINER_STT", "mock")
    monkeypatch.setattr(stt_ws, "_make_vad", lambda: ScriptedVAD([0.9] * 8 + [0.1] * 22))

    with client.websocket_connect(f"/ws/stt?session={session_token}", headers={"origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "ready"
        for _ in range(8):
            socket.send_bytes(CHUNK)
        started = read_until(socket, "turn_start")
        for _ in range(22):
            socket.send_bytes(CHUNK)
        ended = read_until(socket, "turn_end")
        transcript = read_until(socket, "transcript")

    assert started["t_ms"] == 64
    assert ended["audio_ms"] == 960
    assert transcript["text"]
    assert transcript["language"] == "es"
    words = transcript["words"]
    assert words
    assert [word["start_ms"] for word in words] == sorted(word["start_ms"] for word in words)
    assert all(0 <= word["start_ms"] <= word["end_ms"] <= 960 for word in words)
    assert all(0.0 <= word["probability"] <= 1.0 for word in words)

    stored = client.get(f"/api/turns?session={session_token}").json()["turns"]
    assert len(stored) == 1
    assert stored[0]["text"] == transcript["text"]


def test_a_blip_closes_without_a_transcript(monkeypatch: pytest.MonkeyPatch, session_token: str) -> None:
    monkeypatch.setenv("SALES_TRAINER_STT", "mock")
    monkeypatch.setattr(stt_ws, "_make_vad", lambda: ScriptedVAD([0.9] * 2 + [0.1] * 22))

    with client.websocket_connect(f"/ws/stt?session={session_token}", headers={"origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "ready"
        for _ in range(24):
            socket.send_bytes(CHUNK)
        ended = read_until(socket, "turn_end")

    assert ended["audio_ms"] == 768
    assert client.get(f"/api/turns?session={session_token}").json()["turns"] == []
