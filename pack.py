"""预设包（dsp-voicepack/1）的导出与导入。

    python pack.py export <id> <名称> [--target vanilla|nyanko] [--replaces ID]
    python pack.py import <文件> [--overwrite|--rename]
    python pack.py inspect <文件>

导出：从调音台当前面板取预设，按 characters.json 的映射写成包文件。
导入：严格校验后写进面板（服务端 PUT 是原子的——校验不过一个字节都不写）。

"坏包不写一个字节"由服务端保证：它先 Validate 再落盘，400 就是全盘拒绝。
"""
import json
import math
import os
import re
import sys
import uuid
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("BLIP_BASE_URL", "http://127.0.0.1:8731")
ROOT = Path(r"D:\AI\blip-lab")
CHARS = ROOT / "characters.json"
PACKS = ROOT / "packs"

REQUIRED_PARAM_COUNT = 31


def atomic_write(path, contents):
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def call(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method,
                                     headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def read_chars():
    return json.loads(CHARS.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 导出
def export(pack_id, name, target="vanilla", replaces=None):
    characters = read_chars()
    status, snapshot = call("GET", "/api/state")
    if status != 200:
        print("读状态失败", snapshot)
        return 1
    state = snapshot["state"]
    presets = dict(state.get("presets") or {})

    # 内置预设没被改过时不在 state.presets 里，补上出厂定义
    status, meta = call("GET", "/api/meta")
    if status != 200:
        print("读 meta 失败", meta)
        return 1
    for voice in meta.get("voices", []):
        presets.setdefault(voice["label"], [{
            "hz": voice["hz"], "gain": 1.0, "delay": 0.0, "mute": False,
            "p": {key: value for key, value in voice["p"].items() if key != "StartFrequency"},
        }])

    wanted = {row["preset"] for row in characters["characters"]}
    for row in characters["generic"].values():
        wanted.update(row.values())
    missing = sorted(wanted - set(presets))
    if missing:
        print("[FAIL] 面板里缺这些预设，先补齐再导出：", missing)
        return 1

    pack = {
        "format": "dsp-voicepack/1",
        "id": pack_id,
        "name": name,
        "author": "Questing Goose 音色组",
        "version": "1.0.0",
        "target": target,
        "replaces": replaces or [],
        "requires": {"gameBuild": "26284217", "paramCount": REQUIRED_PARAM_COUNT},
        "characters": {row["key"]: row["zh"] for row in characters["characters"]},
        "presets": {label: presets[label] for label in sorted(wanted)},
        "mapping": {row["key"]: row["preset"] for row in characters["characters"]},
    }

    PACKS.mkdir(exist_ok=True)
    if not pack_id or re.search(r'[<>:"/\\|?*\x00-\x1f]', pack_id) or pack_id in (".", ".."):
        print("[FAIL] 非法包文件名")
        return 1
    problem = validate_pack(pack)
    if problem:
        print("[FAIL]", problem)
        return 1
    path = PACKS / f"{pack_id}.json"
    atomic_write(path, json.dumps(pack, ensure_ascii=False, indent=1, allow_nan=False))

    size = path.stat().st_size
    print(f"[OK] {path.name}  {size/1024:.1f} KB")
    print(f"     预设 {len(pack['presets'])} 个 / 角色映射 {len(pack['mapping'])} 条 / target={target}")
    return 0


# ---------------------------------------------------------------- 校验
def validate_pack(pack):
    """在写进游戏之前先做本地检查。错误返回字符串，通过返回 None。"""
    if not isinstance(pack, dict):
        return "不是 JSON 对象"
    if pack.get("format") != "dsp-voicepack/1":
        return f"格式不支持：{pack.get('format')!r}"
    for key in ("id", "name", "presets", "mapping"):
        if key not in pack:
            return f"缺字段 {key}"
    requires = pack.get("requires")
    if not isinstance(requires, dict):
        return "requires 必须是对象"
    if requires.get("paramCount") != REQUIRED_PARAM_COUNT:
        return (f"参数表版本不符：包要 {requires.get('paramCount')} 项，"
                f"当前是 {REQUIRED_PARAM_COUNT} 项。别硬套，会错位")
    if requires.get("gameBuild", "26284217") != "26284217":
        return "游戏版本不兼容，需要 gameBuild=26284217"
    if not isinstance(pack["presets"], dict) or not pack["presets"]:
        return "presets 为空"
    if len(pack["presets"]) > 64:
        return "预设数量超过 64"
    ranges = {}
    for line in (Path(__file__).resolve().parent / "bfxr-param-ranges.txt").read_text().splitlines():
        match = re.match(r"(\w+)\s+default=.*?min=([-\d.]+)\s+max=([-\d.]+)", line)
        if match and match[1] != "StartFrequency":
            ranges[match[1]] = (float(match[2]), 11 if match[1] == "WaveType" else float(match[3]))
    if len(ranges) != REQUIRED_PARAM_COUNT:
        return "本地参数范围表损坏"
    def number(value, low, high):
        return type(value) in (int, float) and math.isfinite(value) and low <= value <= high
    for label, layers in pack["presets"].items():
        if not label.strip() or len(label) > 80 or "|" in label:
            return "非法预设名称"
        if not isinstance(layers, list) or not 1 <= len(layers) <= 8:
            return f"预设「{label}」层数必须是 1-8"
        for layer in layers:
            if not isinstance(layer, dict) or set(layer) != {"hz", "gain", "delay", "mute", "p"}:
                return f"预设「{label}」层字段错误"
            for key in ("hz", "gain", "delay", "mute", "p"):
                if key not in layer:
                    return f"预设「{label}」的层缺字段 {key}"
            if not isinstance(layer["p"], dict) or set(layer["p"]) != set(ranges):
                return f"预设「{label}」需要完整 {REQUIRED_PARAM_COUNT} 项参数"
            if not all(number(layer[key], low, high) for key, low, high in
                       (("hz", 40, 3000), ("gain", 0, 1.5), ("delay", 0, 120))) or type(layer["mute"]) is not bool:
                return f"预设「{label}」层参数类型或范围错误"
            for key, (low, high) in ranges.items():
                value = layer["p"][key]
                if not number(value, low, high) or (key == "WaveType" and value != int(value)):
                    return f"预设「{label}」参数 {key} 类型或范围错误"
    if not isinstance(pack["mapping"], dict) or any(not isinstance(v, str) for v in pack["mapping"].values()):
        return "mapping 必须为字符串映射"
    unknown = set(pack["mapping"].values()) - set(pack["presets"])
    if unknown:
        return f"mapping 指向了不存在的预设：{sorted(unknown)}"
    return None


# ---------------------------------------------------------------- 导入
def import_pack(path, policy):
    if not path.exists():
        print(f"找不到 {path}")
        return 1
    try:
        # utf-8-sig：容忍 Windows 编辑器 / PowerShell 常给 JSON 加的 BOM
        pack = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        print(f"[FAIL] 不是合法 JSON：{exc}")
        return 1

    problem = validate_pack(pack)
    if problem:
        print(f"[FAIL] {problem}")
        return 1

    for _ in range(5):
        status, snapshot = call("GET", "/api/state")
        if status != 200:
            print("读状态失败", snapshot)
            return 1
        state = snapshot["state"]
        presets = dict(state.get("presets") or {})

        clashes = sorted(set(presets) & set(pack["presets"]))
        if policy == "rename":
            for label in clashes:
                new = f"{label}（{pack['id'].split('.')[-1]}）"
                pack["presets"][new] = pack["presets"].pop(label)
            clashes = []

        presets.update(pack["presets"])
        state["presets"] = presets
        if state.get("selectedPreset") in pack["presets"]:
            state["layers"] = pack["presets"][state["selectedPreset"]]
        status, body = call("PUT", "/api/state", {
            "baseRevision": snapshot["revision"], "source": "assistant", "state": state})
        if status == 200:
            print(f"[OK] 导入 {pack['name']} v{pack.get('version','?')}")
            print(f"     新增/覆盖 {len(pack['presets'])} 个预设；"
                  f"当前共 {len(body['state']['presets'])} 个")
            if clashes and policy != "rename":
                print(f"     覆盖了 {len(clashes)} 个同名预设：{clashes}")
            if pack.get("replaces"):
                print(f"     声明取代：{pack['replaces']}")
            return 0
        if status == 409:
            continue
        print(f"  服务端拒绝（HTTP {status}）：{body}")
        return 1
    return 1


def inspect(path):
    pack = json.loads(path.read_text(encoding="utf-8-sig"))
    print(f"id       : {pack.get('id')}")
    print(f"name     : {pack.get('name')}  v{pack.get('version')}")
    print(f"target   : {pack.get('target')}   replaces={pack.get('replaces')}")
    print(f"requires : {pack.get('requires')}")
    print(f"预设     : {len(pack.get('presets', {}))} 个")
    for label, layers in pack.get("presets", {}).items():
        hz = [layer["hz"] for layer in layers]
        print(f"   {label:<14} {len(layers)} 层  hz={hz}")
    problem = validate_pack(pack)
    print("校验     : " + ("通过" if problem is None else "失败 - " + problem))
    return 0 if problem is None else 1


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    command = sys.argv[1]
    if command == "export":
        args = [a for a in sys.argv[2:] if not a.startswith("--")]
        if len(args) < 2:
            print("用法：pack.py export <id> <名称> [--target vanilla|nyanko] [--replaces ID]")
            return 1
        target = "vanilla"
        replaces = None
        rest = sys.argv[2:]
        for i, token in enumerate(rest):
            if token == "--target" and i + 1 < len(rest):
                target = rest[i + 1]
            if token == "--replaces" and i + 1 < len(rest):
                replaces = [rest[i + 1]]
        return export(args[0], args[1], target, replaces)

    if command == "import":
        args = [a for a in sys.argv[2:] if not a.startswith("--")]
        if not args:
            print("用法：pack.py import <文件> [--overwrite|--rename]")
            return 1
        policy = "rename" if "--rename" in sys.argv else "overwrite"
        return import_pack(Path(args[0]), policy)

    if command == "inspect":
        args = [a for a in sys.argv[2:]]
        if not args:
            print("用法：pack.py inspect <文件>")
            return 1
        return inspect(Path(args[0]))

    print(f"未知命令 {command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
