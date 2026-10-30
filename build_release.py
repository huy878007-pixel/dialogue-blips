"""正式的发布打包：一个 Mod，两个音色包。

    player.dialogueblips/
      DialogueBlips.dll
      packs/questinggoose.vanilla.json   原版音色（4 通用 + 18 具名）
      packs/questinggoose.nyanko.json    娘化音色（16 位）

    packs/    导入目录：内置包 + 玩家自己丢进来的包都放这里
    exports/  导出目录：游戏内「导出当前音色包」写到这里，不会被自动加载

正式要求：
  · Release 构建，不是 Debug
  · 带 AGPL-3.0 全文（本项目许可）与 bfxr 的 MPL-2.0 / Apache-2.0
  · 可执行文件分发必须能让接收者拿到源码 —— 仓库目前是私有的，
    所以把源码一并放进包里（AGPL-3.0 §6、MPL-2.0 §3.2 都满足）
  · 版本号取自 manifest，文件名带版本
  · 打包后逐条断言，产出 package-manifest.json 记录哈希

    python build_release.py
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
ENGINE = ROOT / "mod" / "DialogueBlips"
PACKS = ROOT / "packs"
PACK_FILES = ("questinggoose.vanilla.json", "questinggoose.nyanko.json")

FORBIDDEN = ("bfxr-host", "panel.html", "agent.py", "voice-request", "voice-state",
             "overrides.json", ".bak", "console-state", "make_preset", "checks/")


def version_of(mod: Path) -> str:
    return ET.parse(mod / "manifest.xml").getroot().findtext("ModVersion")


def stage_mod(stage: Path) -> int:
    """铺好 Mod 目录，返回源码文件数。"""
    stage.mkdir()
    for source in (ENGINE / "manifest.xml", ENGINE / "characters.json"):
        shutil.copy2(source, stage / source.name)
    for pack in PACK_FILES:
        destination = stage / "packs" / pack
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PACKS / pack, destination)

    # 许可：AGPL 全文 + bfxr 包装层 MIT + 第三方声明 + 两份全文
    shutil.copy2(ROOT / "LICENSE", stage / "LICENSE")
    shutil.copy2(ENGINE / "LICENSE.md", stage / "LICENSE.md")
    shutil.copy2(ENGINE / "Third Party Notices.md", stage / "Third Party Notices.md")
    shutil.copytree(ENGINE / "licenses", stage / "licenses")

    # 源码：AGPL §6 与 MPL §3.2 的源码可得性
    count = 0
    for folder in (ENGINE / "src", ENGINE / "lib" / "bfxr"):
        for file in sorted(folder.glob("*.cs")):
            destination = stage / "source" / folder.name / file.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, destination)
            count += 1
    return count


def main() -> int:
    version = version_of(ENGINE)
    output = ROOT / "dist" / f"release-{version}"
    if output.exists():
        raise SystemExit(f"输出目录已存在，先手动清理：{output}")
    output.mkdir(parents=True)

    build = output / "_build"
    subprocess.run(["dotnet", "build", str(ENGINE), "-c", "Release", "-o", str(build)],
                   check=True, stdout=subprocess.DEVNULL)
    dll = build / "DialogueBlips.dll"
    assert dll.exists(), "Release 构建没有产出 DLL"

    stage = output / "player.dialogueblips"
    source_count = stage_mod(stage)
    shutil.copy2(dll, stage / "DialogueBlips.dll")

    (stage / "安装说明.txt").write_text(
        f"对话音效 · 逐字语音　v{version}\n\n"
        "安装：退出游戏，把 player.dialogueblips 整个文件夹放进游戏的 Mods 目录，再在游戏中启用。\n"
        "升级：保留自己原有的 overrides.json，只替换 DialogueBlips.dll 与 manifest.xml。\n"
        "不需要网页工作台，不需要 Python，也不需要开发用的 .NET 服务。\n\n"
        "操作：F11 打开游戏内设置面板；Esc 关闭；改动停手 0.6 秒自动保存。\n\n"
        "两个目录：\n"
        "  packs/    音色包。内置「原版」与「娘化」两套；想加别人的包，直接把 .json 丢进来，\n"
        "            面板里按刷新即可，不用重启游戏。\n"
        "  exports/  游戏内「导出当前音色包」会写到这里。导出后想让它出现在游戏里，\n"
        "            把文件挪进 packs/ 再刷新。\n\n"
        "娘化音色包：为 16 位有娘化立绘的角色重新设计。需同时启用「深空娘化：可能有点好看」\n"
        "（创意工坊 3828971372）才会自动接管，否则自动退回原版音色。\n"
        "埃莉诺本来就是女性、索耶没有娘化立绘，二者保留原声。\n\n"
        f"许可：AGPL-3.0（全文见 LICENSE）。源码已随包提供，见 source/（{source_count} 个文件）。\n"
        "内置 bfxr 合成器保留原有许可：包装层 MIT，BFXR 部分 MPL-2.0，"
        "SfxrParams/SfxrSynth Apache-2.0。\n"
        "完整声明见 Third Party Notices.md 与 licenses/。\n",
        encoding="utf-8")

    (stage / "源码与许可.txt").write_text(
        "本项目以 GNU AGPL-3.0 发布（见 LICENSE）。\n\n"
        "为什么附带源码：AGPL-3.0 与 MPL-2.0 都要求在分发可执行文件时让接收者能取得对应源码。\n"
        "source/src 下是全部自研源码；source/bfxr 下是被修改过的 bfxr 源文件"
        "（MPL-2.0 文件级 copyleft）。\n"
        "其中 SfxrGenerator.cs 有一处标注 [MOD FIX] 的修改：原包把音量/包络那一行注释掉了，"
        "会导致削波刺耳。\n",
        encoding="utf-8")

    archive = output / f"DialogueBlips-{version}.zip"
    # 只遍历 stage。遍历 output 会把正在写入的 zip 自己也当成条目，
    # 边写边读同一个文件，进程原地打转（曾经吃满 CPU 却产出 0 字节）。
    entries = [f for f in sorted(stage.rglob("*")) if f.is_file()]
    assert archive not in entries, "archive 混进了待打包文件"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as zipped:
        for file in entries:
            zipped.write(file, file.relative_to(stage.parent))
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None, "zip 损坏"
        for name in zipped.namelist():
            low = name.lower()
            assert not any(part in low for part in FORBIDDEN), f"包里有开发文件：{name}"

    manifest = {
        "version": version,
        "archive": archive.name,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest().upper(),
        "dllSHA256": hashlib.sha256(dll.read_bytes()).hexdigest().upper(),
        "packs": list(PACK_FILES),
        "files": sorted(str(f.relative_to(stage)) for f in stage.rglob("*") if f.is_file()),
        "workbenchIncluded": False,
        "userStateIncluded": False,
        "sourceIncluded": True,
    }
    (output / "package-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"PASS release {version}")
    print(f"  {archive.name}  {manifest['sha256'][:16]}...  {len(manifest['files'])} files")
    print(f"  {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
