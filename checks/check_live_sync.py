"""Live-sync regression checks for the tuning console.

Reproduces the two bugs the user hit on 2026-10-30:

  1. Rapid preset switching left several blips playing at once.
     check_browser.py could never catch this because its Audio.play() stub fires
     'ended' after 80 ms, so nothing is ever simultaneously active. Here play()
     is left running until pause() is called, and we count how many are live.

  2. Server-side edits did not reach the page without a reload. Two causes:
     the page treated its own saved revision as a remote change (double audition),
     and a single 409 on save stopped polling for good.

Run:  python checks/check_live_sync.py
Exit 0 = pass.
"""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks" / ".deps"))
from playwright.async_api import async_playwright

BIN = ROOT / "checks" / "http-build" / "bfxrhost.dll"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def api(port, method, body=None):
    url = f"http://127.0.0.1:{port}/api/state"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read())


async def main():
    if not BIN.exists():
        print(f"missing {BIN}; build bfxr-host first")
        return 1

    failures = []
    port = free_port()
    state_path = ROOT / "checks" / f"live-state-{port}.json"
    with (ROOT / "checks" / "live-server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen(["dotnet", str(BIN), "serve", str(port)],
                                  stdout=log, stderr=log,
                                  env={**os.environ, "BLIP_STATE_PATH": str(state_path)})
        try:
            await asyncio.sleep(2.5)
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    headless=True)
                try:
                    page = await browser.new_page(viewport={"width": 1440, "height": 1000})
                    page.set_default_timeout(4000)
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))

                    # Realistic audio stub: only pause() ends playback.
                    await page.add_init_script("""
                      window.__playing = new Set();
                      window.__created = 0;
                      const Base = Audio;
                      window.Audio = class extends Base {
                        constructor(...a){ super(...a); window.__created++; }
                        play(){ window.__playing.add(this); return Promise.resolve(); }
                        pause(){ window.__playing.delete(this); try{ super.pause(); }catch(e){} }
                      };
                    """)
                    await page.goto(f"http://127.0.0.1:{port}")
                    await page.wait_for_function(
                        "document.querySelector('#status').textContent.startsWith('就绪')")

                    async def check(name, test):
                        try:
                            await test()
                            print("PASS", name)
                        except Exception as exc:
                            failures.append(name)
                            print("FAIL", name, str(exc)[:400])

                    # ---- 1. rapid preset switching must not stack audio ----
                    async def no_overlap():
                        names = await page.evaluate("Object.keys(PRESETS)")
                        for name in names[:8]:
                            await page.get_by_role("button", name=name, exact=True).click()
                            await page.wait_for_timeout(90)
                        await page.wait_for_timeout(1200)
                        peak = await page.evaluate("window.__maxPlaying || 0")
                        live = await page.evaluate("window.__playing.size")
                        assert peak <= 1, f"{peak} blips were playing at once"
                        assert live <= 1, f"{live} blips still playing"
                    # track the high-water mark
                    await page.evaluate("""
                      setInterval(()=>{ window.__maxPlaying =
                        Math.max(window.__maxPlaying||0, window.__playing.size); }, 20);
                    """)
                    await check("rapid preset switching never stacks audio", no_overlap)

                    # ---- 2. a server-side edit reaches the open page ----
                    async def remote_edit_visible():
                        snap = api(port, "GET")
                        api(port, "PATCH", {"baseRevision": snap["revision"], "source": "assistant",
                                            "patch": [{"op": "replace", "path": "/layers/0/hz",
                                                       "value": 777}]})
                        await page.wait_for_function(
                            "()=>{const s=[...document.querySelectorAll('input[type=range]')]"
                            ".find(x=>x.max==='3000'); return s && Math.abs(Number(s.value)-777)<1; }",
                            timeout=4000)
                        value = await page.evaluate(
                            "()=>[...document.querySelectorAll('input[type=range]')]"
                            ".find(x=>x.max==='3000').value")
                        assert abs(float(value) - 777) < 1, f"slider shows {value}"
                    await check("server-side edit updates the open page", remote_edit_visible)

                    # ---- 3. interleaved local + remote edits must not deadlock ----
                    async def no_deadlock():
                        before = await page.evaluate("document.querySelector('#status').textContent")
                        # local edit: nudge the hz slider, which queues a save
                        await page.evaluate("""
                          ()=>{const s=[...document.querySelectorAll('input[type=range]')]
                            .find(x=>x.max==='3000');
                            s.value=880; s.dispatchEvent(new Event('input',{bubbles:true}));}
                        """)
                        # remote write lands while the local save is in flight
                        snap = api(port, "GET")
                        api(port, "PATCH", {"baseRevision": snap["revision"], "source": "assistant",
                                            "patch": [{"op": "replace", "path": "/selectedPreset",
                                                       "value": "conflict-probe"}]})
                        await page.wait_for_timeout(2500)
                        banner = await page.evaluate(
                            "()=>document.querySelector('#syncConflict').hidden")
                        status = await page.evaluate(
                            "()=>document.querySelector('#syncStatus').textContent")
                        assert banner is True, f"conflict banner stuck: {status}"
                        assert "冲突" not in status, f"status stuck on conflict: {status}"
                    await check("interleaved edits do not deadlock sync", no_deadlock)

                    # ---- 3b. 并发改不同字段：两边都要留下（字段级合并）----
                    # 之前的实现对 409 是"整份本地状态重试"，会把对方刚写的字段盖回去。
                    async def field_level_merge():
                        snap = api(port, "GET")
                        # 本地改 hz
                        await page.evaluate("""
                          ()=>{const s=[...document.querySelectorAll('input[type=range]')]
                            .find(x=>x.max==='3000');
                            s.value=901; s.dispatchEvent(new Event('input',{bubbles:true}));}
                        """)
                        # 远端在本地保存飞行途中改**另一个**字段
                        api(port, "PATCH", {"baseRevision": snap["revision"], "source": "assistant",
                                            "patch": [{"op": "replace", "path": "/layers/0/gain",
                                                       "value": 0.25}]})
                        await page.wait_for_timeout(2500)
                        after = api(port, "GET")["state"]["layers"][0]
                        assert abs(after["hz"] - 901) < 1, f"local hz lost: {after['hz']}"
                        assert abs(after["gain"] - 0.25) < 0.001, f"remote gain lost: {after['gain']}"
                    await check("concurrent edits to different fields both survive", field_level_merge)

                    # ---- 4. the page keeps polling after all that ----
                    async def still_polling():
                        snap = api(port, "GET")
                        api(port, "PATCH", {"baseRevision": snap["revision"], "source": "assistant",
                                            "patch": [{"op": "replace", "path": "/layers/0/hz",
                                                       "value": 640}]})
                        await page.wait_for_function(
                            "()=>{const s=[...document.querySelectorAll('input[type=range]')]"
                            ".find(x=>x.max==='3000'); return s && Math.abs(Number(s.value)-640)<1; }",
                            timeout=4000)
                    await check("polling still works after a conflict", still_polling)

                    # ---- 5. edits to a preset survive switching away and back ----
                    async def preset_remembered():
                        hz_probe = ("()=>{const s=[...document.querySelectorAll('input[type=range]')]"
                                    ".find(x=>x.max==='3000'); return s ? Number(s.value) : -1; }")
                        await page.get_by_role("button", name="男年轻", exact=True).click()
                        await page.wait_for_timeout(400)
                        await page.evaluate("""()=>{
                          const s=[...document.querySelectorAll('input[type=range]')]
                            .find(x=>x.max==='3000');
                          s.value=523; s.dispatchEvent(new Event('input',{bubbles:true}));}""")
                        await page.wait_for_timeout(1000)      # 等自动保存
                        await page.get_by_role("button", name="女老年", exact=True).click()
                        await page.wait_for_timeout(400)
                        await page.get_by_role("button", name="男年轻", exact=True).click()
                        await page.wait_for_timeout(400)
                        back = await page.evaluate(hz_probe)
                        assert abs(back - 523) < 1, f"切回来变成 {back}，编辑丢了"
                        # 刷新之后也要还在
                        await page.reload()
                        await page.wait_for_function(
                            "document.querySelector('#status').textContent.startsWith('就绪')")
                        await page.get_by_role("button", name="男年轻", exact=True).click()
                        await page.wait_for_timeout(500)
                        after = await page.evaluate(hz_probe)
                        assert abs(after - 523) < 1, f"刷新后变成 {after}，没有持久化"
                    await check("preset edits survive switching away and a reload", preset_remembered)

                    # ---- 6. players can create and delete their own presets ----
                    async def custom_preset():
                        name = "自建测试预设"
                        await page.locator("#presets input[type=text]").fill(name)
                        await page.get_by_role("button", name="+ 新建预设", exact=True).click()
                        await page.wait_for_timeout(700)
                        assert await page.get_by_role("button", name=name, exact=True).is_visible(), \
                            "新建的预设没有出现在列表里"
                        # 存在共享状态里，刷新后还在
                        await page.wait_for_timeout(600)
                        snap = api(port, "GET")
                        assert name in (snap["state"].get("presets") or {}), "新预设没有被持久化"
                        await page.reload()
                        await page.wait_for_function(
                            "document.querySelector('#status').textContent.startsWith('就绪')")
                        assert await page.get_by_role("button", name=name, exact=True).is_visible(), \
                            "刷新后自建预设消失"
                        # 能删掉
                        await page.get_by_role("button", name=name, exact=True).click()
                        await page.wait_for_timeout(400)
                        await page.locator("#presets button.danger").click()
                        await page.wait_for_timeout(700)
                        assert await page.get_by_role("button", name=name, exact=True).count() == 0, \
                            "删除后预设还在"
                        snap = api(port, "GET")
                        assert name not in (snap["state"].get("presets") or {}), "删除没有写回服务端"
                    await check("players can create and delete their own presets", custom_preset)

                    assert not errors, f"page errors: {errors}"
                    print("PASS no browser JS errors")
                finally:
                    await browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill()
            state_path.unlink(missing_ok=True)

    print(f"\nLive-sync checks: {len(failures)} failure(s)")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
