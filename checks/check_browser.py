"""Real headless Chromium checks. No foreground window or audible playback."""
import asyncio
import os
from pathlib import Path
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks" / ".deps"))
from playwright.async_api import async_playwright


async def main():
    failures = []
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with (ROOT / "checks" / "browser-server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(["dotnet", str(ROOT / "checks" / "http-build" / "bfxrhost.dll"), "serve", str(port)],
                                   stdout=log, stderr=log,
                                   env={**os.environ, "BLIP_STATE_PATH": str(ROOT / "checks" / f"browser-state-{port}.json")})
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe", headless=True)
                try:
                    page = await browser.new_page(viewport={"width": 1440, "height": 1000})
                    page.set_default_timeout(3000)
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    await page.add_init_script("""
                      window.__plays=0; window.__audios=[]; window.__liveUrls=new Set();
                      const BaseAudio=Audio;
                      window.Audio=class extends BaseAudio {
                        constructor(...args){super(...args); window.__audios.push(this);}
                      };
                      HTMLMediaElement.prototype.play=function(){
                        window.__plays++; setTimeout(()=>this.dispatchEvent(new Event('ended')),80);
                        return Promise.resolve();
                      };
                      const create=URL.createObjectURL.bind(URL), revoke=URL.revokeObjectURL.bind(URL);
                      URL.createObjectURL=b=>{const u=create(b); __liveUrls.add(u); return u;};
                      URL.revokeObjectURL=u=>{__liveUrls.delete(u); revoke(u);};
                    """)
                    await page.goto(f"http://127.0.0.1:{port}")
                    await page.wait_for_function("document.querySelector('#status').textContent.startsWith('就绪')")

                    async def check(name, test):
                        try:
                            await test()
                            print("PASS", name)
                        except Exception as exc:
                            failures.append(name)
                            print("FAIL", name, str(exc)[:500])

                    async def presets():
                        mismatch = await page.evaluate("""async()=>{
                          const meta=await (await fetch('/api/meta')).json();
                          const names=Object.keys(PRESETS).slice(0,meta.voices.length), wrong=[];
                          names.forEach((name,i)=>Object.entries(meta.voices[i].p).forEach(([k,v])=>{
                            if(k!=='StartFrequency' && Math.abs(PRESETS[name][0].p[k]-v)>1e-6)
                              wrong.push(name+':'+k);
                          })); return wrong;
                        }""")
                        assert not mismatch, str(mismatch)
                    await check("presets match sample generator", presets)

                    async def preset_autoplay():
                        before = await page.evaluate("__plays")
                        await page.get_by_role("button", name="男年轻", exact=True).click()
                        await page.wait_for_timeout(700)
                        assert await page.evaluate("__plays") > before, "enabled autoplay did not play preset"
                    await check("preset change respects autoplay", preset_autoplay)

                    async def newest():
                        calls = 0
                        async def delayed(route):
                            nonlocal calls
                            calls += 1
                            first = calls == 1
                            response = await route.fetch()
                            if first:
                                await asyncio.sleep(.5)
                            await route.fulfill(response=response)
                        await page.route("**/api/voice", delayed)
                        await page.evaluate("""async()=>{
                          layers[0].gain=1; const a=refresh(false);
                          layers[0].gain=.2; const b=refresh(false);
                          await Promise.all([a,b]);
                        }""")
                        await page.unroute("**/api/voice", delayed)
                        matches = await page.evaluate("""async()=>{
                          const actual=await (await fetch(document.querySelector('#dlSingle').href)).arrayBuffer();
                          const expected=await fetchWav('/api/voice',buildForm());
                          const a=new Uint8Array(actual), b=new Uint8Array(expected);
                          return a.length===b.length && a.every((v,i)=>v===b[i]);
                        }""")
                        assert matches, "stale response replaced the newest WAV"
                    await check("latest request wins", newest)

                    async def urls():
                        await page.evaluate("async()=>{for(let i=0;i<5;i++) await refresh(false);}")
                        live = await page.evaluate("__liveUrls.size")
                        assert live <= 2, f"{live} unreleased WAV URLs"
                    await check("old WAV URLs are released", urls)

                    async def parameter_tiers():
                        await page.get_by_role("button", name="基础参数", exact=True).click()
                        assert await page.get_by_label("音高 Hz", exact=True).is_visible()
                        assert not await page.get_by_label("镶边扫描", exact=True).is_visible()
                        await page.get_by_role("button", name="高阶参数", exact=True).click()
                        assert await page.get_by_label("镶边扫描", exact=True).is_visible()
                        await page.get_by_role("button", name="进阶参数", exact=True).click()
                        assert await page.get_by_label("颤音幅度", exact=True).is_visible()
                        await page.get_by_role("button", name="基础参数", exact=True).click()
                    await check("three parameter tiers preserve the values", parameter_tiers)

                    async def remote_state():
                        snap = await (await page.request.get(f"http://127.0.0.1:{port}/api/state")).json()
                        result = await page.request.patch(f"http://127.0.0.1:{port}/api/state", data={
                            "baseRevision": snap["revision"], "source": "assistant", "patch": [
                                {"op": "replace", "path": "/layers/0/hz", "value": 880},
                                {"op": "replace", "path": "/sentence/throttle", "value": 50}]})
                        assert result.status == 200
                        await page.wait_for_function("document.querySelector('[data-key=hz]').value==='880'")
                        assert await page.locator("#throttle").input_value() == "50"
                        assert "助手" in await page.locator("#syncStatus").inner_text()
                    await check("API updates reach the visible controls", remote_state)

                    async def browser_state():
                        await page.get_by_label("音高 Hz", exact=True).evaluate("el=>{el.value='930';el.dispatchEvent(new Event('input',{bubbles:true}));}")
                        await page.wait_for_function("document.querySelector('#syncStatus').textContent.includes('已同步')")
                        snap = await (await page.request.get(f"http://127.0.0.1:{port}/api/state")).json()
                        assert snap["state"]["layers"][0]["hz"] == 930
                        await page.reload()
                        await page.wait_for_function("document.querySelector('[data-key=hz]')?.value==='930'")
                    await check("browser edits sync back and survive reload", browser_state)

                    async def conflict_resolution():
                        # 契约在 2026-10-30 变了：撞一次 409 不再弹横幅停摆，
                        # 而是拿最新 revision 重试一次，后写者（本地）优先。
                        # 之前那个"横幅出现 + 手动选保留哪个"的流程会让轮询永久卡死，
                        # 用户报的就是"看不到助手的修改、要刷新"。所以这里断言的是新契约：
                        # 本地改动不丢、不出现横幅、同步继续。
                        intercepted = False
                        async def collide(route):
                            nonlocal intercepted
                            if route.request.method == "PUT" and not intercepted:
                                intercepted = True
                                snapshot = await (await page.request.get(f"http://127.0.0.1:{port}/api/state")).json()
                                await page.request.patch(f"http://127.0.0.1:{port}/api/state", data={
                                    "baseRevision":snapshot["revision"],"source":"assistant","patch":[
                                        {"op":"replace","path":"/layers/0/gain","value":.7}]})
                            await route.continue_()
                        await page.route("**/api/state", collide)
                        await page.get_by_label("音高 Hz", exact=True).evaluate("el=>{el.value='950';el.dispatchEvent(new Event('input',{bubbles:true}));}")
                        await page.unroute("**/api/state", collide)
                        await page.wait_for_function("document.querySelector('#syncStatus').textContent.includes('已同步')")
                        assert not await page.locator("#syncConflict").is_visible(), "冲突横幅不该再卡住"
                        assert await page.get_by_label("音高 Hz", exact=True).input_value() == "950", "本地改动被远端覆盖"
                        snapshot = await (await page.request.get(f"http://127.0.0.1:{port}/api/state")).json()
                        assert snapshot["state"]["layers"][0]["hz"] == 950, "本地改动没有真正写回服务端"
                    await check("simultaneous edits resolve automatically without locking sync", conflict_resolution)
                    await page.screenshot(path=str(ROOT / "checks" / "panel-review.png"), full_page=True)

                    await page.set_viewport_size({"width": 390, "height": 844})
                    assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                    await page.screenshot(path=str(ROOT / "checks" / "panel-mobile-review.png"), full_page=True)

                    await page.goto((ROOT / "listen.html").as_uri())
                    await page.wait_for_function("__audios[0] && __audios[0].duration > 0")
                    async def repeats():
                        await page.locator(".row").first.click()
                        await page.wait_for_timeout(1000)
                        count = await page.evaluate("__plays")
                        assert count == 3, f"short note played {count} time(s), expected 3"
                    await check("static page repeats a short note three times", repeats)
                    async def no_errors():
                        assert not errors, str(errors)
                    await check("no browser JS errors", no_errors)
                finally:
                    await browser.close()
        finally:
            process.terminate()
            process.wait(timeout=10)
    print(f"Browser checks: {len(failures)} failure(s)")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
