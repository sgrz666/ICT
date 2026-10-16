"""基准评测自动化回归测试（§7.4 / §1.2）。"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_screening_benchmark_passes_100_percent():
    runner_script = ROOT / "benchmarks" / "runner.py"
    res = subprocess.run(
        [sys.executable, str(runner_script), "--profile", "screening"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Benchmark runner failed:\n{res.stdout}\n{res.stderr}"
    assert "Overall Pass Rate: 12/12 (100.0%)" in res.stdout
