"""Extract the game's localization string tables from the CURRENT installed build.

The old 游戏本地化文本.json has no known provenance (the sprite extractor next to it
reads the Demo folder), so this rebuilds it straight from the shipped Addressables
bundles instead of trusting it.

Unity Localization splits the data in two:
  <Table> Shared Data  (localization-assets-shared)  -> m_Entries[{m_Id, m_Key}]
  <Table>_<locale>      (localization-string-tables-<locale>)
                                                     -> m_TableData[{m_Id, m_Localized}]
so join them on m_Id.

Output: 游戏本地化文本_正式版.json  [{table, key, zh, en}, ...]
"""
import json
import sys
from pathlib import Path

import UnityPy

GAME_DATA = Path(r"D:\SteamLibrary\steamapps\common\Probably Stolen\Probably Stolen_Data")
BUNDLE_DIR = GAME_DATA / "StreamingAssets" / "aa" / "StandaloneWindows64"
SHARED = BUNDLE_DIR / "localization-assets-shared_assets_all.bundle"
ZH = BUNDLE_DIR / "localization-string-tables-chinese(simplified)(zh)_assets_all.bundle"
EN = BUNDLE_DIR / "localization-string-tables-english(en)_assets_all.bundle"
OUT = Path(r"D:\AI\blip-lab\游戏本地化文本_正式版.json")


def table_name(obj_name: str) -> str:
    """'ClientName_zh' / 'ClientName Shared Data' -> 'ClientName'"""
    for suffix in (" Shared Data", "_zh", "_en"):
        if obj_name.endswith(suffix):
            return obj_name[: -len(suffix)]
    return obj_name


def read_shared(path: Path) -> dict[str, dict[int, str]]:
    """table -> {id: key}"""
    out: dict[str, dict[int, str]] = {}
    env = UnityPy.load(str(path))
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        data = obj.read()
        name = getattr(data, "m_Name", "") or ""
        if not name.endswith("Shared Data"):
            continue
        tree = obj.read_typetree()
        entries = tree.get("m_Entries") or []
        out[table_name(name)] = {int(e["m_Id"]): e["m_Key"] for e in entries if "m_Id" in e}
    return out


def read_locale(path: Path) -> dict[str, dict[int, str]]:
    """table -> {id: localized text}"""
    out: dict[str, dict[int, str]] = {}
    if not path.exists():
        return out
    env = UnityPy.load(str(path))
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        data = obj.read()
        name = getattr(data, "m_Name", "") or ""
        if not (name.endswith("_zh") or name.endswith("_en")):
            continue
        tree = obj.read_typetree()
        entries = tree.get("m_TableData") or []
        out[table_name(name)] = {int(e["m_Id"]): (e.get("m_Localized") or "")
                                 for e in entries if "m_Id" in e}
    return out


def main() -> int:
    for path in (SHARED, ZH):
        if not path.exists():
            print(f"missing bundle: {path}")
            return 1

    shared = read_shared(SHARED)
    zh = read_locale(ZH)
    en = read_locale(EN)

    rows = []
    for table, keys in sorted(shared.items()):
        zh_map = zh.get(table, {})
        en_map = en.get(table, {})
        for entry_id, key in keys.items():
            rows.append({"table": table, "key": key,
                         "zh": zh_map.get(entry_id, ""),
                         "en": en_map.get(entry_id, "")})

    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    filled = sum(1 for r in rows if r["zh"])
    print(f"tables={len(shared)} entries={len(rows)} with_zh={filled}")
    for table in sorted(shared):
        print(f"  {table:16s} keys={len(shared[table]):5d} zh={len(zh.get(table, {})):5d}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
