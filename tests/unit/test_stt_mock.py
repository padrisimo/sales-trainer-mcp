from sales_trainer.voice.stt.mock import CONFIDENCES, TEXT, MockSTTProvider

BYTES_PER_MS = 32


def test_mock_returns_text_language_and_words() -> None:
    result = MockSTTProvider().transcribe(b"\x00" * (BYTES_PER_MS * 1600))
    assert result.text == TEXT
    assert result.language == "es"
    assert len(result.words) == len(TEXT.split())
    first = result.words[0]
    assert set(first.model_dump()) == {"word", "start_ms", "end_ms", "probability"}


def test_mock_timings_are_ordered_and_inside_the_turn() -> None:
    audio_ms = 1600
    result = MockSTTProvider().transcribe(b"\x00" * (BYTES_PER_MS * audio_ms))
    starts = [word.start_ms for word in result.words]
    assert starts == sorted(starts)
    assert all(0 <= word.start_ms <= word.end_ms <= audio_ms for word in result.words)


def test_mock_probabilities_are_bounded_and_fixed() -> None:
    result = MockSTTProvider().transcribe(b"\x00" * (BYTES_PER_MS * 1600))
    assert [word.probability for word in result.words] == CONFIDENCES
    assert all(0.0 <= value <= 1.0 for value in CONFIDENCES)
