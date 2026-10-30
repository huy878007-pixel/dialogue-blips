"""Build a clean local player test package; never bundles the development workbench."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
MOD = ROOT / "mod/DialogueBlips"
version = ET.parse(MOD / "manifest.xml").getroot().findtext("ModVersion")
output = ROOT / "dist" / f"player-{version}-test"
output.mkdir(parents=True, exist_ok=False)
build = output / "build"
subprocess.run(["dotnet", "build", str(MOD), "-c", "Release", "-o", str(build)], check=True)
stage = output / "player.dialogueblips"
stage.mkdir()
for source, name in [
    (build / "DialogueBlips.dll", "DialogueBlips.dll"),
    (MOD / "manifest.xml", "manifest.xml"),
    (MOD / "characters.json", "characters.json"),
    (MOD / "LICENSE.md", "LICENSE.md"),
    (MOD / "Third Party Notices.md", "Third Party Notices.md"),
    (ROOT / "packs/questinggoose.vanilla.json", "packs/questinggoose.vanilla.json"),
]:
    destination = stage / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
shutil.copytree(MOD / "licenses", stage / "licenses")
(stage / "安装说明.txt").write_text(
    f"对话音效 {version} 玩家测试包\n\n"
    "退出游戏后，把 player.dialogueblips 整个文件夹放进游戏 Mods 目录，再在游戏中启用。\n"
    "升级已有安装时保留自己的 overrides.json，不要删除原目录。\n"
    "无需启动网页工作台，也不需要安装 Python 或开发用 .NET 10 服务。\n"
    "F11 打开游戏内设置面板；Agent 文件轮询仅在面板可见时运行，关闭或隐藏即暂停。\n"
    "本测试包只含原版音色包；娘化机制试验包尚未作为正式音色发布。\n"
    "本版通过自动回归；真实游戏启停、跨场景和长期音频内存仍需验收。\n", encoding="utf-8")
archive = output / f"DialogueBlips-{version}-player-test.zip"
with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as zipped:
    for file in sorted(stage.rglob("*")):
        if file.is_file():
            zipped.write(file, file.relative_to(output))
with zipfile.ZipFile(archive) as zipped:
    for name in zipped.namelist():
        assert not any(part in name.lower() for part in ("bfxr-host", "panel.html", "agent.py", "voice-request", "voice-state", "overrides.json", ".bak")), name
    assert zipped.testzip() is None
    dll = zipped.read("player.dialogueblips/DialogueBlips.dll")
    assert dll == (build / "DialogueBlips.dll").read_bytes()
manifest = {"version": version, "dllSHA256": hashlib.sha256(dll).hexdigest().upper(),
            "archive": str(archive), "files": sorted(str(file.relative_to(stage)) for file in stage.rglob("*") if file.is_file()),
            "workbenchIncluded": False, "userStateIncluded": False}
(output / "package-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print("PASS clean player package:", archive)
print("DLL SHA256:", manifest["dllSHA256"])
