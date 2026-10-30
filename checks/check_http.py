"""Build and test an isolated server; never stops an existing user process."""
import concurrent.futures
import http.client
import io
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
import urllib.parse
import wave

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "checks" / "http-build"


def main():
    subprocess.run(["dotnet", "build", str(ROOT / "bfxr-host"), "-o", str(OUT)], check=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    failures = []

    def request(path, fields=None, method=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=8)
        try:
            body = urllib.parse.urlencode(fields) if isinstance(fields, dict) else fields
            conn.request(method or ("POST" if fields is not None else "GET"), path, body,
                         {"Content-Type": "application/x-www-form-urlencoded"})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def check(name, test):
        try:
            test()
            print("PASS", name)
        except Exception as exc:
            failures.append(name)
            print("FAIL", name, str(exc))

    def expect(value, message):
        assert value, message

    def peak(data):
        with wave.open(io.BytesIO(data)) as wav:
            raw = wav.readframes(wav.getnframes())
        return max(abs(x[0]) for x in struct.iter_unpack("<h", raw))

    with (ROOT / "checks" / "http-server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(["dotnet", str(OUT / "bfxrhost.dll"), "serve", str(port)],
                                   stdout=log, stderr=log, cwd=ROOT,
                                   env={**os.environ, "BLIP_STATE_PATH": str(ROOT / "checks" / f"http-state-{port}.json")})
        try:
            for _ in range(80):
                try:
                    request("/api/meta")
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("server did not start")
            check("panel works from custom build directory", lambda: expect(
                b"<!DOCTYPE html>" in request("/")[1], "panel missing"))
            check("unknown route returns 404", lambda: expect(request("/missing")[0] == 404, "wrong status"))
            check("wrong method returns 405", lambda: expect(
                request("/api/meta", method="DELETE")[0] == 405, "wrong status"))
            for key, value in [("layer0.hz", "NaN"), ("layer0.hz", "-1"),
                               ("layer0.gain", "Infinity"), ("interval", "0"),
                               ("layer0.WaveType", "12"), ("layer0.WaveType", "2.5"),
                               ("layer0.DecayTime", "999")]:
                check("reject " + key + "=" + value, lambda k=key, v=value: expect(
                    request("/api/sentence", {k: v, "text": "abc"})[0] == 400, "expected 400"))
            voice = {"layer0.hz": "1056", "layer0.WaveType": "4", "layer0.DecayTime": ".18",
                     "layer0.CompressionAmount": "0"}

            def volume_check():
                loud = peak(request("/api/voice", {**voice, "layer0.gain": "1"})[1])
                quiet = peak(request("/api/voice", {**voice, "layer0.gain": ".2"})[1])
                expect(abs(quiet / loud - .2) < .01, f"quiet/loud={quiet/loud:.3f}")
            check("gain actually controls exported volume", volume_check)
            check("form plus decodes as a space", lambda: expect(
                request("/api/sentence", "layer0.WaveType=4&text=a+b&interval=90&throttle=20&jitter=0")[1]
                == request("/api/sentence", "layer0.WaveType=4&text=a%20b&interval=90&throttle=20&jitter=0")[1],
                "plus parsed as voiced character"))

            def oversized():
                with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
                    sock.settimeout(5)
                    sock.sendall(b"POST /api/voice HTTP/1.1\r\nHost: localhost\r\nContent-Length: 999999\r\n\r\n")
                    expect(b" 413 " in sock.recv(1024), "expected immediate 413")
            check("oversized body rejected before reading", oversized)
            check("valid form larger than the old 32 KiB buffer", lambda: expect(
                request("/api/voice", {**voice, "padding": "x" * 40000})[0] == 200, "expected 200"))

            def incomplete_body():
                with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
                    sock.settimeout(5)
                    sock.sendall(b"POST /api/voice HTTP/1.1\r\nHost: localhost\r\nContent-Length: 10\r\n\r\nx")
                    expect(b" 408 " in sock.recv(1024), "expected timeout response")
            check("incomplete body has a deadline", incomplete_body)
            check("sentence has a duration budget", lambda: expect(
                request("/api/sentence", {"text": "," * 300})[0] == 400, "expected 400"))

            def concurrent_rendering():
                expected = request("/api/voice", voice)
                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                    actual = list(pool.map(lambda _: request("/api/voice", voice), range(40)))
                expect(all(item == expected for item in actual), "concurrent WAVs differ")
            check("concurrent HTTP rendering", concurrent_rendering)
            check("service recovers after malformed requests", lambda: expect(
                request("/api/meta")[0] == 200, "server unavailable"))

            def get_state():
                status, data = request("/api/state")
                expect(status == 200, f"GET state returned {status}")
                return json.loads(data)

            def update(snapshot, patch, method="PATCH"):
                fields = {"baseRevision": snapshot["revision"], "source": "test"}
                fields.update({"patch": patch} if method == "PATCH" else {"state": patch})
                return request("/api/state", json.dumps(fields), method=method)

            def defaults():
                data = get_state()
                expect(data["state"]["sentence"]["throttle"] == 55, "default cadence changed")
                expect(len(data["state"]["layers"]) == 1, "missing initial voice")
            check("shared state has current defaults", defaults)

            def patch_state():
                before = get_state()
                status, data = update(before, [{"op": "replace", "path": "/layers/0/hz", "value": 900}])
                after = json.loads(data)
                expect(status == 200 and after["revision"] == before["revision"] + 1, "revision did not advance")
                expect(after["state"]["layers"][0]["hz"] == 900, "pitch did not change")
                expect(after["state"]["layers"][0]["p"] == before["state"]["layers"][0]["p"], "unrelated parameters changed")
            check("remote patch changes only the requested parameter", patch_state)

            def conflict():
                before = get_state()
                update(before, [{"op": "replace", "path": "/layers/0/gain", "value": .8}])
                status, _ = update(before, [{"op": "replace", "path": "/layers/0/gain", "value": .1}])
                expect(status == 409 and get_state()["state"]["layers"][0]["gain"] == .8, "stale state overwrote edits")
            check("stale writes return 409 without overwriting", conflict)

            def atomic_validation():
                before = get_state()
                status, _ = update(before, [
                    {"op": "replace", "path": "/layers/0/hz", "value": 650},
                    {"op": "replace", "path": "/layers/0/p/WaveType", "value": 12}])
                expect(status == 400 and get_state() == before, "invalid patch partially applied")
            check("invalid patch is atomic", atomic_validation)

            def replace_state():
                before = get_state()
                before["state"]["sentence"]["text"] = "你好，实时调音！"
                status, data = update(before, before["state"], "PUT")
                expect(status == 200 and json.loads(data)["state"]["sentence"]["text"] == "你好，实时调音！", "PUT lost Unicode text")
            check("browser can replace and save the complete state", replace_state)
            check("malformed state JSON returns 400", lambda: expect(
                request("/api/state", "{broken", method="PATCH")[0] == 400, "invalid JSON accepted"))

            def persistence():
                saved = json.loads((ROOT / "checks" / f"http-state-{port}.json").read_text(encoding="utf-8-sig"))
                expect(saved == get_state(), "persisted snapshot differs")
            check("shared state is persisted", persistence)
        finally:
            process.terminate()
            process.wait(timeout=10)
    print(f"HTTP checks: {len(failures)} failure(s)")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
