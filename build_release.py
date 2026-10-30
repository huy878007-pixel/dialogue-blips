"""正式的发布打包：产出两个独立的 Mod 包。

    Mod A  player.dialogueblips          引擎 + 原版音色包
    Mod B  player.dialogueblips.nyanko   娘化音色包（纯数据，依赖 A 与娘化立绘）

正式要求（与开发期的 player 测试包不同）：
  · Release 构建，不是 Debug
  · 每个包都带 AGPL-3.0 全文（本项目许可）与 bfxr 的 MPL-2.0 / Apache-2.0
  · 可执行文件分发必须能让接收者拿到对应源码 —— 仓库目前是私有的，
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
NYANKO = ROOT / "mod" / "DialogueBlipsNyanko"
PACKS = ROOT / "packs"

FORBIDDEN = ("bfxr-host", "panel.html", "agent.py", "voice-request", "voice-state",
             "overrides.json", ".bak", "console-state", "make_preset", "checks/")

SOURCE_EXT = (".cs",)


def version_of(mod: Path) -> str:
    return ET.parse(mod / "manifest.xml").getroot().findtext("ModVersion")


def copy_licences(stage: Path) -> None:
    shutil.copy2(ROOT / "LICENSE", stage / "LICENSE")                 # AGPL-3.0 全文
    shutil.copy2(ENGINE / "LICENSE.md", stage / "LICENSE.md")          # bfxr 包装层 MIT
    shutil.copy2(ENGINE / "Third Party Notices.md", stage / "Third Party Notices.md")
    shutil.copytree(ENGINE / "licenses", stage / "licenses")


def copy_source(stage: Path) -> int:
    """把本项目的源码放进包里，满足 AGPL / MPL 的源码可得性。"""
    target = stage / "source"
    count = 0
    for folder in (ENGINE / "src", ENGINE / "lib" / "bfxr"):
        for file in sorted(folder.glob("*.cs")):
            destination = target / folder.name / file.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, destination)
            count += 1
    return count


def textfile(stage: Path, name: str, body: str) -> None:
    (stage / name).write_text(body, encoding="utf-8")


def zip_stage(output: Path, stage: Path, archive_name: str) -> Path:
    archive = output / archive_name
    # 只遍历 stage 目录。遍历 output 会把正在写入的 zip 自己也当成条目，
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
    return archive


def main() -> int:
    engine_version = version_of(ENGINE)
    nyanko_version = version_of(NYANKO)
    assert engine_version == nyanko_version, "两个 Mod 的版本号必须一致"

    output = ROOT / "dist" / f"release-{engine_version}"
    if output.exists():
        raise SystemExit(f"输出目录已存在，先手动清理：{output}")
    output.mkdir(parents=True)

    build = output / "_build"
    subprocess.run(["dotnet", "build", str(ENGINE), "-c", "Release", "-o", str(build)],
                   check=True, stdout=subprocess.DEVNULL)
    dll = build / "DialogueBlips.dll"
    assert dll.exists(), "Release 构建没有产出 DLL"

    # ---- Mod A ----
    stage_a = output / "player.dialogueblips"
    stage_a.mkdir()
    for source, name in [
        (dll, "DialogueBlips.dll"),
        (ENGINE / "manifest.xml", "manifest.xml"),
        (ENGINE / "characters.json", "characters.json"),
        (PACKS / "questinggoose.vanilla.json", "packs/questinggoose.vanilla.json"),
    ]:
        destination = stage_a / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    copy_licences(stage_a)
    source_count = copy_source(stage_a)
    textfile(stage_a, "安装说明.txt",
             f"对话音效 · 逐字语音　v{engine_version}\n\n"
             "安装：退出游戏，把 player.dialogueblips 整个文件夹放进游戏的 Mods 目录，再在游戏中启用。\n"
             "升级：保留自己原有的 overrides.json，只替换 DialogueBlips.dll 与 manifest.xml。\n"
             "不需要网页工作台，不需要 Python，也不需要开发用的 .NET 服务。\n\n"
             "操作：F11 打开游戏内设置面板；Esc 关闭；改动停手 0.6 秒自动保存。\n"
             "设置面板里可以切音色包、调每个角色的音高/亮度/尾长等参数、增删发声层、导出自己的音色包。\n\n"
             f"许可：AGPL-3.0（全文见 LICENSE）。源码已随包提供，见 source/。\n"
             "内置 bfxr 合成器保留原有许可：包装层 MIT，BFXR 部分 MPL-2.0，SfxrParams/SfxrSynth Apache-2.0。\n"
             "完整声明见 Third Party Notices.md 与 licenses/。\n\n"
             f"本包共 {source_count} 个源码文件，可在 AGPL/MPL 要求下重新构建。\n")
    textfile(stage_a, "源码与许可.txt",
             "本项目以 GNU AGPL-3.0 发布（见 LICENSE）。\n\n"
             "为什么附带源码：AGPL-3.0 与 MPL-2.0 都要求在分发可执行文件时让接收者能取得对应源码。\n"
             "source/ 下是全部自研源码；lib/bfxr 下是被修改过的 bfxr 源文件（MPL-2.0 文件级 copyleft）。\n"
             "其中 SfxrGenerator.cs 有一处标注 [MOD FIX] 的修改：原包把音量/包络那一行注释掉了，会导致削波刺耳。\n")
    archive_a = zip_stage(output, stage_a, f"DialogueBlips-{engine_version}.zip")

    # ---- Mod B ----
    stage_b = output / "player.dialogueblips.nyanko"
    (stage_b / "packs").mkdir(parents=True)
    shutil.copy2(NYANKO / "manifest.xml", stage_b / "manifest.xml")
    shutil.copy2(PACKS / "questinggoose.nyanko.json",
                 stage_b / "packs" / "questinggoose.nyanko.json")
    shutil.copy2(ROOT / "LICENSE", stage_b / "LICENSE")
    textfile(stage_b, "安装说明.txt",
             f"对话音效 · 娘化音色包　v{nyanko_version}\n\n"
             "这是什么：为 16 位有娘化立绘、且原本为男性的角色重新设计的专属音色。纯数据包，不含程序集。\n\n"
             "前置：\n"
             "  · 对话音效 · 逐字语音（player.dialogueblips）\n"
             "  · 深空娘化：可能有点好看（创意工坊 3828971372）\n\n"
             "安装：退出游戏，把 player.dialogueblips.nyanko 整个文件夹放进 Mods 目录并启用。\n"
             "启用后自动接管默认音色；在 F11 面板的「音色包」下拉里可以随时切回原版。\n"
             "关掉本 Mod 即干净退回原版音色，不会留下残留。\n\n"
             "不参与的两个角色：\n"
             "  · 埃莉诺 —— 本来就是女性，保留原声\n"
             "  · 索耶 —— 没有娘化立绘，保留原声\n\n"
             "许可：AGPL-3.0（全文见 LICENSE）。本包不含可执行代码。\n")
    archive_b = zip_stage(output, stage_b, f"DialogueBlips-Nyanko-{nyanko_version}.zip")

    # ---- 清单 ----
    manifest = {
        "version": engine_version,
        "mods": {
            "player.dialogueblips": {
                "archive": archive_a.name,
                "sha256": hashlib.sha256(archive_a.read_bytes()).hexdigest().upper(),
                "dllSHA256": hashlib.sha256(dll.read_bytes()).hexdigest().upper(),
                "files": sorted(str(f.relative_to(stage_a)) for f in stage_a.rglob("*") if f.is_file()),
            },
            "player.dialogueblips.nyanko": {
                "archive": archive_b.name,
                "sha256": hashlib.sha256(archive_b.read_bytes()).hexdigest().upper(),
                "files": sorted(str(f.relative_to(stage_b)) for f in stage_b.rglob("*") if f.is_file()),
            },
        },
        "workbenchIncluded": False,
        "userStateIncluded": False,
        "sourceIncluded": True,
    }
    (output / "package-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"PASS release {engine_version}")
    for key, entry in manifest["mods"].items():
        print(f"  {entry['archive']}  {entry['sha256'][:16]}…  {len(entry['files'])} 个文件")
    print(f"  输出目录：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
