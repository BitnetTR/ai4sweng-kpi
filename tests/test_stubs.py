import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_committed_stub_is_up_to_date_with_metrics_json():
    script = ROOT / "scripts" / "gen_stubs.py"
    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "ai4sweng/__init__.pyi is out of date with metrics.json.\n"
        + result.stdout
        + result.stderr
    )
