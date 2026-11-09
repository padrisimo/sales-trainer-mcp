from sales_trainer.voice.tts.base import VisemeEvent

# Same 15 names, same order, as src/sales_trainer/web/static/js/visemes.js.
VISEMES = [
    "sil",
    "PP",
    "FF",
    "TH",
    "DD",
    "kk",
    "CH",
    "SS",
    "nn",
    "RR",
    "aa",
    "E",
    "I",
    "O",
    "U",
]

# Azure viseme IDs 0-21 to our set. Spanish has phonemes with no Oculus counterpart
# (h, l, r), so they land on the closest shape instead of being dropped.
AZURE_VISEME_TO_VISEME = {
    0: "sil",
    1: "aa",
    2: "aa",
    3: "O",
    4: "E",
    5: "RR",
    6: "I",
    7: "U",
    8: "O",
    9: "aa",
    10: "O",
    11: "aa",
    12: "aa",
    13: "RR",
    14: "DD",
    15: "SS",
    16: "CH",
    17: "TH",
    18: "FF",
    19: "DD",
    20: "kk",
    21: "PP",
}

MERGE_WINDOW_MS = 60


def azure_to_viseme(azure_id: int) -> str:
    return AZURE_VISEME_TO_VISEME.get(azure_id, "sil")


def smooth(events: list[VisemeEvent], merge_window_ms: int = MERGE_WINDOW_MS) -> list[VisemeEvent]:
    """Drop duplicates that would flicker the mouth, keeping the timeline monotonic."""
    out: list[VisemeEvent] = []
    for event in sorted(events, key=lambda item: item.t_ms):
        if event.t_ms < 0:
            continue
        if out and out[-1].viseme == event.viseme and event.t_ms - out[-1].t_ms <= merge_window_ms:
            continue
        out.append(event)
    return out
