"""Pull per-character dialogue out of the game's localization dump so voice
design can be based on who the character actually is, not on the name.

Input : 提取工具与映射/游戏本地化文本.json  -> [{key, zh, en}, ...]
Output: 人物剧情_2026-10-30.md              -> one section per character
"""
import json
import re
import sys
from pathlib import Path

SRC = Path(r"D:\AI\blip-lab\游戏本地化文本_正式版.json")
OUT = Path(r"D:\AI\blip-lab\人物剧情_2026-10-30.md")

# 名单来自 15_正式版角色盘点/有名字角色与待补立绘.md（1.01 版盘点）
# 顺序 = 已做立绘的 8 位在前，待做的在后
CHARS = [
    ("georgio",   "乔治奥",      ("georgio",)),
    ("eleanor",   "埃莉诺",      ("eleanor",)),
    ("serpico",   "塞尔皮科",    ("serpico",)),
    ("lun",       "伦警官",      ("lun", "officer")),
    ("jackson",   "杰克逊博士",  ("jackson", "drjackson")),
    ("landlord",  "房东",        ("landlord",)),
    ("mentor",    "导师",        ("mentor",)),
    ("joe",       "乔·王尔德",   ("joe",)),
    ("nellis",    "内利斯",      ("nellis",)),
    ("sawyer",    "索耶",        ("sawyer",)),
    ("cheng",     "程大爷",      ("grandpa_cheng", "cheng")),
    ("butcher",   "屠夫",        ("butcher",)),
    ("odin",      "奥丁",        ("odin",)),
    ("lou",       "卢",          ("lou",)),
    ("ashish",    "阿希什",      ("ashish",)),
]

MAX_LINES = 14          # 每个角色最多引多少句


def main():
    if not SRC.exists():
        print(f"missing {SRC}")
        return 1
    entries = json.loads(SRC.read_text(encoding="utf-8"))
    by_key = {e["key"]: e for e in entries if isinstance(e, dict) and "key" in e}

    sections = []
    for slug, zh_name, prefixes in CHARS:
        # 中文名
        name = ""
        for p in prefixes:
            hit = by_key.get("name_" + p) or by_key.get("name_" + p + "_name")
            if hit and hit.get("zh"):
                name = hit["zh"]
                break
        # 对话：key 里含 dialog_ 且包含任一前缀，且不是其他角色的
        dialogs = []
        for key, entry in by_key.items():
            if not key.startswith("dialog_"):
                continue
            low = key.lower()
            if not any(p in low for p in prefixes):
                continue
            zh = (entry.get("zh") or "").strip()
            if zh:
                dialogs.append((key, zh))
        dialogs.sort()

        if not name and not dialogs:
            sections.append(f"## {zh_name}\n\n（本地化库里没有找到该角色的文本，可能只出现在通缉数据里）\n")
            continue

        lines = [f"## {zh_name}" + (f"（游戏内名：{name}）" if name else ""), ""]
        lines.append(f"- 对话条目数：**{len(dialogs)}**")
        if dialogs:
            lines.append("")
            for key, zh in dialogs[:MAX_LINES]:
                one = re.sub(r"\s+", " ", zh)
                lines.append(f"- `{key}` — {one}")
            if len(dialogs) > MAX_LINES:
                lines.append(f"- …还有 {len(dialogs) - MAX_LINES} 条")
        sections.append("\n".join(lines) + "\n")

    header = ["# 人物剧情提炼（自动抽取，供音色设计参考）", "",
              f"来源：`{SRC.name}`（{len(entries)} 条）　生成脚本：`build_plot.py`", "",
              "> 只抽了 `dialog_*` 条目，没有人工润色。**台词量多的角色不等于戏份重**——",
              "> 有些是循环交易台词。真正的剧情权重看 `15_正式版角色盘点` 与通缉数据。", ""]
    OUT.write_text("\n".join(header) + "\n".join(sections), encoding="utf-8")
    print(f"-> {OUT}")
    for s in sections:
        first = s.splitlines()[0]
        count = re.search(r"\*\*(\d+)\*\*", s)
        print(f"  {first:<28} 条目 {count.group(1) if count else '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
