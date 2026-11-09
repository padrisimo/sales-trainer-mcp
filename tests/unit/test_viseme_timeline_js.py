import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_viseme_timeline_script_passes() -> None:
    result = subprocess.run(
        ["node", str(ROOT / "tests" / "js" / "viseme_timeline.mjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "viseme timeline ok" in result.stdout
