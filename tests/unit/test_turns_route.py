import uuid

from fastapi.testclient import TestClient

from sales_trainer.voice.stt.base import Word
from sales_trainer.voice.turns import Turn, get_turn_store
from sales_trainer.web.app import app

client = TestClient(app)


def test_an_unknown_session_returns_no_turns() -> None:
    assert client.get("/api/turns?session=missing").json() == {"turns": []}


def test_turns_come_back_in_order_with_their_words() -> None:
    token = f"route-{uuid.uuid4()}"
    store = get_turn_store()
    store.add(
        token,
        Turn(
            audio=b"",
            audio_ms=320,
            text="Hola.",
            language="es",
            words=[Word(word="Hola", start_ms=0, end_ms=100, probability=0.9)],
        ),
    )
    store.add(token, Turn(audio=b"", audio_ms=640, text="Adiós.", language="es"))

    body = client.get(f"/api/turns?session={token}").json()

    assert [turn["text"] for turn in body["turns"]] == ["Hola.", "Adiós."]
    assert body["turns"][0]["audio_ms"] == 320
    assert body["turns"][0]["words"][0] == {"word": "Hola", "start_ms": 0, "end_ms": 100, "probability": 0.9}
    assert body["turns"][1]["words"] == []
