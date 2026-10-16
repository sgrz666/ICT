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


def test_model_profiles_require_key_and_report_skipped():
    import os
    runner_script = ROOT / "benchmarks" / "runner.py"
    env = {k: v for k, v in os.environ.items() if k.lower() not in ("deepseek_api_key", "deepseek")}
    env["DEEPSEEK_API_KEY"] = ""
    env["deepseek"] = ""

    for profile in ("deepseek_direct", "agent_graph"):
        res = subprocess.run(
            [sys.executable, str(runner_script), "--profile", profile],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=env,
        )
        assert res.returncode == 0
        assert "requires DEEPSEEK_API_KEY (currently unset)" in res.stdout
        report = ROOT / "output" / "eduforge" / "reports" / f"benchmark-{profile}.json"
        assert report.exists()
        import json
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["status"] == "SKIPPED"
        assert "DEEPSEEK_API_KEY" in data["reason"]
