"""Isolated voice-pack CLI regressions; never contacts the live 8731 service."""
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parent


def main():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="blip-pack-check-") as folder:
        temp = Path(folder)
        with (temp / "server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen(
                ["dotnet", str(ROOT / "checks/http-build/bfxrhost.dll"), "serve", str(port)],
                stdout=log, stderr=log,
                env={**os.environ, "BLIP_STATE_PATH": str(temp / "state.json")})
            failures = []
            count = 0

            def snapshot():
                with urllib.request.urlopen(base + "/api/state", timeout=5) as response:
                    return json.loads(response.read())

            def check(name, doc, expected=True, raw=None, bom=False):
                nonlocal count
                count += 1
                path = temp / f"case-{count}.json"
                path.write_text(raw if raw is not None else json.dumps(doc, ensure_ascii=False),
                                encoding="utf-8-sig" if bom else "utf-8")
                before = snapshot()
                result = subprocess.run(
                    [sys.executable, str(ROOT / "pack.py"), "import", str(path), "--overwrite"],
                    cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                    env={**os.environ, "BLIP_BASE_URL": base, "PYTHONIOENCODING": "utf-8"})
                after = snapshot()
                good = (result.returncode == 0 and after["revision"] == before["revision"] + 1) if expected else (
                    result.returncode != 0 and before == after)
                print(("PASS " if good else "FAIL ") + name)
                if not good:
                    failures.append(name)
                    print(result.stdout, result.stderr)

            try:
                for attempt in range(50):
                    try:
                        snapshot()
                        break
                    except OSError:
                        if attempt == 49:
                            raise
                        time.sleep(.1)
                good = json.loads((ROOT / "packs/questinggoose.vanilla.json").read_text(encoding="utf-8-sig"))
                check("valid pack imports", good)
                check("invalid syntax does not change state", None, False, raw='{"broken":')
                mutations = [
                    ("wrong parameter version", lambda p: p["requires"].update(paramCount=999)),
                    ("wrong game version", lambda p: p["requires"].update(gameBuild="wrong")),
                    ("missing parameter", lambda p: next(iter(p["presets"].values()))[0]["p"].pop("BitCrush")),
                    ("too many layers", lambda p: p["presets"].update(probe=[next(iter(p["presets"].values()))[0]] * 9)),
                    ("unknown mapping target", lambda p: p["mapping"].update(probe="absent")),
                    ("non-finite pitch", lambda p: next(iter(p["presets"].values()))[0].update(hz=float("nan"))),
                    ("fractional waveform", lambda p: next(iter(p["presets"].values()))[0]["p"].update(WaveType=2.5)),
                    ("wrong presets type", lambda p: p.update(presets=[])),
                    ("wrong layer type", lambda p: p["presets"].update(probe=["bad"])),
                ]
                for name, mutate in mutations:
                    bad = copy.deepcopy(good)
                    mutate(bad)
                    check(name + " rejected atomically", bad, False)
                check("UTF-8 BOM accepted", good, bom=True)
                # 出厂的两个包也要过同一套校验：娘化包曾经因为 mapping 指向
                # 不存在的预设而在游戏里整个载入失败，网页端完全看不出来。
                for shipped in ("questinggoose.vanilla.json", "questinggoose.nyanko.json"):
                    check("shipped " + shipped + " is valid",
                          json.loads((ROOT / "packs" / shipped).read_text(encoding="utf-8-sig")))
            finally:
                server.terminate()
                server.wait(timeout=8)
            print(f"Pack checks: {count-len(failures)}/{count} passed")
            return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
