"""Minimal character card test: numbers and prompts load as expected."""
import pytest
import yaml


@pytest.mark.parametrize("path, exp", [
    ("characters/nivel1.yaml", (50, 75, 10)),
    ("characters/nivel2.yaml", (30, 80, 10)),
    ("characters/nivel3.yaml", (10, 85, 8)),
])
def test_card_numbers_match_memory(path, exp):
    with open(path) as f:
        m = yaml.safe_load(f)
    assert m["start_temperature"] == exp[0]
    assert m["threshold"] == exp[1]
    assert m["max_turns"] == exp[2]


def test_every_prompt_file_is_loaded_as_text():
    prompts = ["characters/prompts/nivel1.md",
               "characters/prompts/nivel2.md",
               "characters/prompts/nivel3.md"]
    for p in prompts:
        with open(p) as f:
            txt = f.read()
        assert txt and len(txt) > 800, f"{p} too short or empty"
