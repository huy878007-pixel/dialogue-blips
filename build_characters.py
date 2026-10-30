"""生成人物键表 characters.json —— Mod 运行时靠它把 NPC 认成人。

为什么不用 identifier：一个角色有十几个（georgio1..georgio12 / abby1..abby5）。
为什么不用 displayName：那是本地化字符串，切语言就变。

方案：用本地化 key（name_xxx）做稳定身份。运行时拿
    LocHelper.GetLocalizedClientName(key)
现算出当前语言下的显示名，和 storeClient.displayName 比对 —— 语言无关且精确。
撞名时（name_lun 和 name_officer_lun 都叫「伦警官」）退化到 spriteName。

本脚本只产出数据 + 做校验，不改游戏。
校验两件事：
  1. 每个 nameKey 在本版本地化表里真实存在
  2. 每个 preset 名在调音台面板里真实存在
"""
import json
import sys
import urllib.request
from pathlib import Path

LOC = Path(r"D:\AI\blip-lab\游戏本地化文本_正式版.json")
OUT = Path(r"D:\AI\blip-lab\characters.json")
BASE = "http://127.0.0.1:8731"

# 通用音色：LocGender × LocRegister 四种组合，覆盖 ~110 个原型角色
GENERIC = {
    "MALE":   {"FORMAL": "男老", "INFORMAL": "男年轻"},
    "FEMALE": {"FORMAL": "女老年",        "INFORMAL": "女年轻"},
    "NEUTRAL": {"FORMAL": "女老年",       "INFORMAL": "女年轻"},
}

# 特殊角色：(人物键, 本地化 key 链, 预设名, 分类, 已知 spriteName)
# nameKey 链 = 按优先级尝试；游戏里同一角色常有好几个 key（如 name_lun / name_officer_lun）
SPECIAL = [
    ("georgio",       ["name_georgio"],                       "乔治奥",       "story",  ["george"]),
    ("eleanor",       ["name_eleanor"],                       "埃莉诺",       "story",  ["eleanor", "eleanor_scav", "eleanor_rev"]),
    ("serpico",       ["name_serpico"],                       "塞尔皮科",     "story",  ["serpico", "serpico_scav", "serpico_rev"]),
    ("officer_lun",   ["name_officer_lun", "name_lun"],       "伦警官",       "story",  ["officer_lun"]),
    ("lou",           ["name_lou"],                           "卢",           "story",  ["lou"]),
    ("mentor",        ["name_mentor", "name_the_mentor"],     "导师",         "tutorial", ["mentor", "the_mentor"]),
    ("landlord",      ["name_landlord", "name_the_landlord"], "房东",         "tutorial", ["landlord", "the_landlord"]),
    ("sawyer",        ["name_sawyer"],                        "索耶",         "tutorial", ["sawyer"]),
    ("joe_wild",      ["name_joe_wild", "name_joe"],          "乔·王尔德",    "tutorial", ["joe"]),
    ("dr_jackson",    ["name_dr._jackson"],                   "杰克逊博士",   "tutorial", []),
    ("the_butcher",   ["name_the_butcher"],                   "屠夫",         "wanted", []),
    ("odin",          ["name_odin"],                          "奥丁",         "wanted", []),
    ("juan",          ["name_juan"],                          "胡安",         "wanted", []),
    ("arthur_lafleur", ["name_arthur_lafleur"],               "亚瑟·拉弗勒",  "wanted", []),
    ("james_bailey",  ["name_james_bailey"],                  "詹姆斯·贝利",  "wanted", []),
    ("john_smith",    ["name_john_smith"],                    "约翰·史密斯",  "wanted", []),
    ("li_bei_wen",    ["name_li_bei_wen"],                    "李北文",       "wanted", []),
    ("leroy",         ["name_leroy"],                         "勒鲁瓦",       "wanted", []),
]


def panel_presets():
    """面板里能点的所有预设名。

    注意：内置预设只要用户没改过就**不在** state.presets 里（那里只存改动），
    它只出现在 /api/meta 的 voices 里。所以两边都要取。
    """
    with urllib.request.urlopen(BASE + "/api/state", timeout=10) as response:
        state = json.loads(response.read())["state"]
    names = set((state.get("presets") or {}).keys())
    with urllib.request.urlopen(BASE + "/api/meta", timeout=10) as response:
        meta = json.loads(response.read())
    names.update(voice["label"] for voice in meta.get("voices", []))
    return names


def main():
    if not LOC.exists():
        print(f"缺本地化文件 {LOC}，先跑 extract_localization.py")
        return 1
    entries = json.loads(LOC.read_text(encoding="utf-8"))
    names = {e["key"]: e["zh"] for e in entries if e["table"] == "ClientName"}

    available = panel_presets()

    errors = []
    characters = []
    for key, name_keys, preset, tier, sprites in SPECIAL:
        found = [(nk, names[nk]) for nk in name_keys if nk in names]
        if not found:
            errors.append(f"{key}: 本地化里找不到 {name_keys}")
            continue
        if preset not in available:
            errors.append(f"{key}: 面板里没有预设「{preset}」")
            continue
        characters.append({
            "key": key,
            "nameKeys": [nk for nk, _ in found],   # 按优先级
            "zh": found[0][1],
            "preset": preset,
            "tier": tier,
            "spriteNames": sprites,
        })

    for preset in {p for row in GENERIC.values() for p in row.values()}:
        if preset not in available:
            errors.append(f"通用音色「{preset}」在面板里不存在")

    doc = {
        "format": "dsp-characters/1",
        "note": "人物键表。nameKeys 按优先级尝试；运行时用 GetLocalizedClientName 现算显示名比对。",
        "generic": GENERIC,
        "characters": characters,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"角色 {len(characters)}/{len(SPECIAL)}，通用组合 {len(GENERIC)} 组")
    for row in characters:
        print(f"  {row['key']:<18} {row['zh']:<10} -> {row['preset']:<12} [{row['tier']}] "
              f"keys={len(row['nameKeys'])} sprites={len(row['spriteNames'])}")
    if errors:
        print("\n[FAIL] problems:")
        for e in errors:
            print("   -", e)
        return 1
    print(f"\n[OK] all checks passed -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
