import re
from pathlib import Path

from sales_trainer.voice.tts.base import VisemeEvent
from sales_trainer.voice.visemes import (
    AZURE_VISEME_TO_VISEME,
    VISEMES,
    azure_to_viseme,
    smooth,
)

ROOT = Path(__file__).resolve().parents[2]
VISEMES_JS = ROOT / "src" / "sales_trainer" / "web" / "static" / "js" / "visemes.js"


def test_azure_mapping_covers_every_id() -> None:
    assert set(AZURE_VISEME_TO_VISEME) == set(range(22))


def test_azure_mapping_targets_are_known_visemes() -> None:
    assert set(AZURE_VISEME_TO_VISEME.values()) <= set(VISEMES)


def test_unknown_azure_id_falls_back_to_silence() -> None:
    assert azure_to_viseme(99) == "sil"


def test_smooth_keeps_the_timeline_monotonic() -> None:
    events = [
        VisemeEvent(t_ms=300, viseme="aa", weight=1.0),
        VisemeEvent(t_ms=100, viseme="PP", weight=1.0),
    ]
    assert [event.t_ms for event in smooth(events)] == [100, 300]


def test_smooth_drops_duplicates_inside_the_window() -> None:
    events = [
        VisemeEvent(t_ms=0, viseme="aa", weight=1.0),
        VisemeEvent(t_ms=40, viseme="aa", weight=1.0),
        VisemeEvent(t_ms=400, viseme="aa", weight=1.0),
    ]
    assert [event.t_ms for event in smooth(events)] == [0, 400]


def test_smooth_keeps_a_real_change_of_shape() -> None:
    events = [
        VisemeEvent(t_ms=0, viseme="aa", weight=1.0),
        VisemeEvent(t_ms=40, viseme="PP", weight=1.0),
    ]
    assert [event.viseme for event in smooth(events)] == ["aa", "PP"]


def test_python_and_javascript_viseme_lists_match() -> None:
    source = VISEMES_JS.read_text(encoding="utf-8")
    block = re.search(r"export const VISEMES = \[(.*?)\];", source, re.DOTALL)
    assert block is not None
    js_names = re.findall(r'"([^"]+)"', block.group(1))
    assert js_names == VISEMES
