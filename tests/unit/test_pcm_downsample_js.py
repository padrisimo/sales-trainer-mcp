import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pcm_downsample_script_passes() -> None:
    result = subprocess.run(
        ["node", str(ROOT / "tests" / "js" / "pcm_downsample.mjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "pcm downsample ok" in result.stdout
