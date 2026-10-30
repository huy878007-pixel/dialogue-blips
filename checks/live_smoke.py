"""Read-only smoke check of the deployed lab; headless, with audio disabled."""
import asyncio
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks/.deps"))
from playwright.async_api import async_playwright


def state():
    with urllib.request.urlopen("http://127.0.0.1:8731/api/state", timeout=5) as response:
        return json.loads(response.read())


async def main():
    before = state()
    errors = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe", headless=True)
        try:
            page = await browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.add_init_script("HTMLMediaElement.prototype.play=()=>Promise.resolve();")
            await page.goto("http://127.0.0.1:8731/")
            await page.wait_for_function("document.querySelector('#status').textContent.startsWith('就绪')")
            await page.wait_for_timeout(800)
            hz = await page.get_by_label("音高 Hz", exact=True).first.input_value()
            assert float(hz) == before["state"]["layers"][0]["hz"]
            assert not errors, errors
            await page.screenshot(path=str(ROOT / "checks/repair-results/live-console.png"), full_page=True)
        finally:
            await browser.close()
    assert state() == before, "The read-only browser visit modified the document"
    print(f"PASS deployed console loads without JS errors; state revision {before['revision']} preserved")


if __name__ == "__main__":
    asyncio.run(main())
