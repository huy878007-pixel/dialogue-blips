"""Run the repair suite with private services; save individual logs and exit codes."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "checks/repair-results"
OUT.mkdir(exist_ok=True)
PYTHON = sys.executable
TASKS = [
    ("mod-build", ["dotnet", "build", "mod/DialogueBlips", "-c", "Release", "-o", "checks/fix-build"]),
    ("mod-logic", ["dotnet", "run", "--project", "checks/review-20261030/ReviewHarness.csproj"]),
    ("mod-edge-cases", ["dotnet", "run", "--project", "checks/full-audit-20261030-r2/Audit.csproj", "-c", "Release"]),
    ("synth-engine", ["dotnet", "run", "--project", "checks/Checks.csproj"]),
    ("http", [PYTHON, "checks/check_http.py"]),
    ("browser", [PYTHON, "checks/check_browser.py"]),
    ("live-sync", [PYTHON, "checks/check_live_sync.py"]),
    ("web-boundaries", [PYTHON, "checks/review-20261030/review_web.py"]),
    ("pack-cli", [PYTHON, "test_pack.py"]),
    ("agent-cli", [PYTHON, "checks/review-20261030/test_agent_cli.py"]),
    ("python-syntax", [PYTHON, "-m", "py_compile", "agent.py", "pack.py", "test_pack.py",
                       "checks/check_browser.py", "checks/check_live_sync.py", "checks/run_regressions.py"]),
]
results = []
for name, command in TASKS:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=120,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    (OUT / f"{name}.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    results.append({"name": name, "exitCode": result.returncode})
    print(f"{'PASS' if result.returncode == 0 else 'FAIL'} {name}", flush=True)
    if result.returncode:
        print(result.stdout, result.stderr, flush=True)
(OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
raise SystemExit(any(result["exitCode"] for result in results))
