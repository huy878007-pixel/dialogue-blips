"""Agent 接口的命令行工具：不手写 JSON 也能实时改音色。

    python agent.py state                         # 看当前状态
    python agent.py set 乔治奥 0 hz 90             # 改第 0 层音高
    python agent.py set 乔治奥 0 Overtones 0.3     # 改泛音
    python agent.py preview 乔治奥                  # 试听
    python agent.py pack 原版音色包                 # 切包
    python agent.py batch "乔治奥|0|hz=90" "乔治奥|0|BitCrush=0.1"

请先打开游戏内 F11 控制面板。面板可见时模组每 500 ms 检查请求；关闭或隐藏时暂停。
"""
import json
import os
import msvcrt
import sys
import time
import uuid
from pathlib import Path

MOD = Path(r"D:\SteamLibrary\steamapps\common\Probably Stolen"
           r"\Mods\player.dialogueblips")
REQ = MOD / "voice-request.json"
STATE = MOD / "voice-state.json"


def read_state():
    if not STATE.exists():
        return None
    try:
        return json.loads(STATE.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"error": str(exc)}


def send(payload, wait=True):
    # The mailbox is single-writer. Windows releases this lock if the process exits.
    with (MOD / "voice-request.lock").open("a+b") as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b"0")
            lock.flush()
        deadline = time.monotonic() + 5
        while True:
            try:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    print("其他调音请求仍在等待回执，请稍后重试")
                    return 1
                time.sleep(.1)
        try:
            if REQ.exists():
                pending = json.loads(REQ.read_text(encoding="utf-8-sig"))
                state = read_state() or {}
                if pending.get("id") and pending["id"] != state.get("lastRequest"):
                    print("上一个请求尚未处理，保留原请求；请先打开游戏内 F11 面板")
                    return 1
            return _send_locked(payload, wait)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def _send_locked(payload, wait):
    payload = dict(payload, id=uuid.uuid4().hex)
    # allow_nan=False rejects NaN/Infinity before any file is changed.
    contents = json.dumps(payload, ensure_ascii=False, indent=1, allow_nan=False)
    temp = REQ.with_name(REQ.name + "." + payload["id"] + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, REQ)
    finally:
        temp.unlink(missing_ok=True)
    if not wait:
        print("已发送，不等回执")
        return 0
    for _ in range(40):                      # 最多等 4 秒
        time.sleep(0.1)
        state = read_state()
        if state and state.get("lastRequest") == payload["id"]:
            if state.get("requestStatus") == "rejected":
                print("请求被拒绝：", state.get("requestError", "未知原因"))
                return 1
            print("已应用：", json.dumps(state, ensure_ascii=False, indent=1))
            return 0
    print("等了 4 秒没回执——请确认游戏运行且 F11 面板已打开；关闭时请求保留，等待下次打开")
    return 1


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]

    if cmd == "state":
        state = read_state()
        print("没有 voice-state.json（游戏还没跑过）" if state is None
              else json.dumps(state, ensure_ascii=False, indent=1))
        return 0

    if cmd == "set":
        if len(sys.argv) != 6:
            print("用法：agent.py set <预设> <层> <参数> <值>")
            return 1
        preset, layer, slot, value = sys.argv[2:6]
        return send({"set": {f"{preset}|{layer}|{slot}": float(value)}})

    if cmd == "batch":
        pairs = {}
        for item in sys.argv[2:]:
            key, _, value = item.partition("=")
            if not key or not _:
                print(f"请求未发送，缺少 = 号：{item}")
                return 1
            pairs[key] = float(value)
        if not pairs:
            print("没有可用的参数")
            return 1
        return send({"set": pairs})

    if cmd == "preview":
        if len(sys.argv) != 3:
            print("用法：agent.py preview <预设>")
            return 1
        return send({"audition": sys.argv[2]})

    if cmd == "pack":
        if len(sys.argv) != 3:
            print("用法：agent.py pack <显示名或文件名>")
            return 1
        return send({"pack": sys.argv[2]})

    print(f"未知命令 {cmd}")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as exc:
        print("请求未完成：", exc)
        sys.exit(1)
