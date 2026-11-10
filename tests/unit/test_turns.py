from sales_trainer.voice.turns import Turn, TurnDetector, TurnStore

CHUNK = b"\x00\x00" * 512


def start(detector: TurnDetector) -> None:
    detector.push(CHUNK, 0.9)
    assert detector.push(CHUNK, 0.9).started is True


def test_a_single_high_chunk_does_not_start_a_turn() -> None:
    detector = TurnDetector()
    assert detector.push(CHUNK, 0.9).started is False
    assert detector.active is False


def test_two_consecutive_high_chunks_start_a_turn() -> None:
    detector = TurnDetector()
    start(detector)
    assert detector.active is True


def test_a_low_chunk_resets_the_start_counter() -> None:
    detector = TurnDetector()
    detector.push(CHUNK, 0.9)
    detector.push(CHUNK, 0.1)
    assert detector.push(CHUNK, 0.9).started is False
    assert detector.push(CHUNK, 0.9).started is True


def test_700_ms_of_silence_closes_the_turn() -> None:
    detector = TurnDetector()
    start(detector)
    for _ in range(21):
        assert detector.push(CHUNK, 0.1).ended is None
    update = detector.push(CHUNK, 0.1)
    assert update.ended is not None
    assert update.ended.audio_ms == 24 * 32
    assert detector.active is False


def test_a_blip_shorter_than_250_ms_of_speech_is_discarded() -> None:
    detector = TurnDetector()
    start(detector)
    update = detector.push(CHUNK, 0.1)
    for _ in range(21):
        update = detector.push(CHUNK, 0.1)
    assert update.ended is not None
    assert update.discarded is True


def test_the_turn_force_closes_at_30_seconds() -> None:
    detector = TurnDetector()
    start(detector)
    update = detector.push(CHUNK, 0.9)
    for _ in range(935):
        update = detector.push(CHUNK, 0.9)
    assert update.ended is not None
    assert update.ended.audio_ms >= 30_000


def test_the_turn_keeps_every_chunk() -> None:
    detector = TurnDetector()
    start(detector)
    update = detector.push(CHUNK, 0.1)
    for _ in range(21):
        update = detector.push(CHUNK, 0.1)
    assert update.ended is not None
    assert len(update.ended.audio) == 24 * len(CHUNK)


def test_store_returns_a_copy_and_keeps_order() -> None:
    store = TurnStore()
    store.add("s", Turn(audio=b"", audio_ms=320, text="uno", language="es"))
    store.add("s", Turn(audio=b"", audio_ms=640, text="dos", language="es"))
    turns = store.list("s")
    assert [turn.text for turn in turns] == ["uno", "dos"]
    turns.clear()
    assert len(store.list("s")) == 2
