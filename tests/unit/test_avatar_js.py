import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_avatar_smoke_script_passes() -> None:
    result = subprocess.run(
        ["node", str(ROOT / "tests" / "js" / "avatar_smoke.mjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "avatar smoke ok" in result.stdout
