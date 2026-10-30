"""从原版音色包生成娘化验证包。

只是**机制验证版**：保留所有预设名（所以 characters.json 的映射完全不用改），
把每个角色的音区按名次映射进女声段，层间的失谐比例保持不变。
好听不好听另说，目的是跑通"两个包、可切换、可回退"这条链路。

    python make_nyanko.py
"""
import json
import io
import sys
from pathlib import Path

ROOT = Path(r"D:\AI\blip-lab")
SRC = ROOT / "packs" / "questinggoose.vanilla.json"
DST = ROOT / "packs" / "questinggoose.nyanko.json"
MOD_PACKS = Path(r"D:\SteamLibrary\steamapps\common\Probably Stolen"
                 r"\Mods\player.dialogueblips\packs")

LOW, HIGH = 520.0, 1000.0   # 女声段


def main():
    if not SRC.exists():
        print(f"缺原版包 {SRC}，先跑 pack.py export")
        return 1
    doc = json.loads(SRC.read_text(encoding="utf-8-sig"))
    presets = doc["presets"]

    # 只娘化**具名角色**。普通 NPC（那四个通用音色）保持原样——
    # 用户 2026-10-30 明确：立绘只做了特殊角色的娘化，普通男性 NPC 没有。
    chars = json.loads((ROOT / "characters.json").read_text(encoding="utf-8-sig"))
    named = {row["preset"] for row in chars["characters"]}

    primary = {}
    for name, layers in presets.items():
        if layers and name in named:
            primary[name] = float(layers[0].get("hz", 200.0))

    ordered = sorted(primary, key=lambda n: primary[n])
    count = len(ordered)
    target = {}
    for i, name in enumerate(ordered):
        target[name] = LOW if count == 1 else LOW + (HIGH - LOW) * i / (count - 1)

    out = json.loads(json.dumps(doc))          # 深拷贝
    for name, layers in out["presets"].items():
        if not layers or name not in primary:
            continue                            # 通用音色原样保留
        factor = target[name] / max(primary[name], 1.0)
        for layer in layers:
            layer["hz"] = round(max(40.0, min(3000.0, float(layer["hz"]) * factor)), 2)

    out["id"] = "questinggoose.nyanko"
    out["name"] = "娘化音色包（验证版）"
    out["target"] = "nyanko"
    out["replaces"] = ["questinggoose.vanilla"]
    # 只有配套的娘化立绘模组一起启用时，这个包才会自动接管默认
    out["requiresMod"] = "3828971372"
    out["version"] = "0.1.0"
    out["note"] = ("机制验证版：只把 18 个具名角色的音区按名次移进女声段，"
                   "通用音色（男年轻/男老/女年轻/女老年）保持原样——"
                   "立绘只娘化了特殊角色，普通男性 NPC 没有。层间失谐比例保持。")

    DST.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[OK] {DST.name}  {DST.stat().st_size / 1024:.1f} KB")

    print(f"\n{'角色':<14}{'原 Hz':>8}{'娘化 Hz':>10}")
    for name in ordered:
        print(f"{name:<14}{primary[name]:8.0f}{target[name]:10.0f}")

    MOD_PACKS.mkdir(parents=True, exist_ok=True)
    (MOD_PACKS / DST.name).write_text(DST.read_text(encoding="utf-8"), encoding="utf-8-sig")
    print(f"\n已复制到 {MOD_PACKS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
