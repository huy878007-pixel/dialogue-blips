"""Extract the character -> spriteName -> identifier map from the decompiled
StoreClientUniqueList.

Why this matters: StoreClient.identifier is NOT a stable character key.
One character owns many identifiers (abby1..abby5, georgio1..georgio5,
georgioSerpicoLetter...). spriteName is the asset name and is the closest thing
to a stable per-character key the game exposes.

Output:
  persona-map.json  machine-readable: [{key, spriteNames[], identifiers[], nameKey}]
  persona-map.md    human-readable table, grouped by spriteName
"""
import json
import os
import re
import sys
from pathlib import Path

SOURCES = [Path(p) for p in sys.argv[1:]] or [Path(r"C:\Users\Administrator\Desktop\深空当铺人物美化\15_正式版角色盘点\正式版固定角色代码对照.cs")]
OUT = Path(r"D:\AI\blip-lab")

METHOD_RE = re.compile(r"^\s*(?:public|private|internal|protected)\s+(?:static\s+)?StoreClient\s+(\w+)\s*\(")
IDENT_RE = re.compile(r'\.identifier\s*=\s*"([^"]*)"')
SPRITE_RE = re.compile(r'\.spriteName\s*=\s*"([^"]*)"')
NAME_RE = re.compile(r'GetLocalizedClientName\("name_([A-Za-z0-9_]+)"\)')
WANTED_RE = re.compile(r'SetWanted\("([^"]*)"\)')


def main():
    for src in SOURCES:
        if not src.exists():
            print(f"missing {src}")
            return 1

    methods = []
    current = None
    for src in SOURCES:
      for line in src.read_text(encoding="utf-8").splitlines():
          m = METHOD_RE.match(line)
          if m:
              current = {"method": m.group(1), "ids": [], "sprites": [], "names": [], "wanted": []}
              methods.append(current)
              continue
          if current is None:
              continue
          current["ids"] += IDENT_RE.findall(line)
          current["sprites"] += SPRITE_RE.findall(line)
          current["names"] += NAME_RE.findall(line)
          current["wanted"] += WANTED_RE.findall(line)
  
    # group by spriteName (a character may reuse a sprite across variants);
    # fall back to nameKey, then to the method name.
    groups = {}
    for method in methods:
        sprite = method["sprites"][0] if method["sprites"] else ""
        name = method["names"][0] if method["names"] else ""
        key = sprite or name or method["method"]
        groups.setdefault(key, {"key": key, "spriteNames": [], "identifiers": [],
                                "nameKeys": [], "methods": [], "wanted": []})
        g = groups[key]
        for s in method["sprites"]:
            if s and s not in g["spriteNames"]:
                g["spriteNames"].append(s)
        for i in method["ids"]:
            if i and i not in g["identifiers"]:
                g["identifiers"].append(i)
        for n in method["names"]:
            if n and n not in g["nameKeys"]:
                g["nameKeys"].append(n)
        if method["method"] not in g["methods"]:
            g["methods"].append(method["method"])
        for w in method["wanted"]:
            if w and w not in g["wanted"]:
                g["wanted"].append(w)

    entries = sorted(groups.values(), key=lambda g: (g["key"]))
    (OUT / "persona-map.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 人物映射（草稿 · 自动生成，勿手改）", "",
             f"来源：{', '.join(p.name for p in SOURCES)}　方法数 {len(methods)}　分组 {len(entries)}", "",
             "> **这是草稿，不是权威映射。** 行级正则解析不了跨类的方法边界，",
             "> 只在单一类（如 `StoreClientUniqueList`）上干净。指向全量 `Assembly-CSharp` 时会把",
             "> 相邻方法串在一起（实测 `george` 组混进了 serpico 的 identifier）。",
             "> 要拿去驱动运行时查找，必须先换成按花括号配对的解析，并逐个核对。",
             "> 特殊 NPC 的**权威名单**以 `15_正式版角色盘点/有名字角色与待补立绘.md` 为准。", "",
             "**键是 `spriteName`**——`identifier` 一个角色有好多个，不能当键。",
             "但 `spriteName` 也有反例：`maleBM5` 被两个角色共用，`eleanor`/`eleanor_scav` 是同一角色两套图。", "",
             "| spriteName | 本地化名 key | identifier（部分） | 创建方法 |",
             "|---|---|---|---|"]
    for g in entries:
        ids = ", ".join(f"`{i}`" for i in g["identifiers"][:4])
        if len(g["identifiers"]) > 4:
            ids += f" …(+{len(g['identifiers']) - 4})"
        names = ", ".join(f"`{n}`" for n in g["nameKeys"]) or "—"
        methods_ = ", ".join(g["methods"][:3]) + ("…" if len(g["methods"]) > 3 else "")
        lines.append(f"| `{g['key']}` | {names} | {ids or '—'} | {methods_} |")
    (OUT / "persona-map.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"方法数 {len(methods)}，去重后 {len(entries)} 组")
    print(f"-> {OUT / 'persona-map.json'}")
    print(f"-> {OUT / 'persona-map.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
