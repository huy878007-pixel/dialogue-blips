"""生成娘化音色包（特调版 v2）。

只重做有娘化立绘、且原本是男性的角色。**埃莉诺本来就是女性，不参与**（保留原声）。
4 个通用音色 + 索耶 + 埃莉诺 逐字节保留。

音区：305–1308 Hz，避开包里不动的 女老年 620 / 埃莉诺 764 / 女年轻 1056（各 1.2 半音）。

**材质**只用稳定有声高的波形，噪声类只做低增益辅音层：
  0 方波   1 锯齿   2 正弦   4 三角   7 哨音   8 破波(Breaker)
不用：
  3 白噪 / 5 粉噪 / 9 位噪 / 11 Buzz  → 只在辅音/气声层低增益
  6 Tan / 10 Combo                    → 刺耳或每 4 相位换波形，不稳定

    python make_nyanko_design.py                  # 用设计表生成
    python make_nyanko_design.py --from-console   # 从调音台回写（去掉（娘化）后缀）
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(r"D:\AI\blip-lab")
SRC = ROOT / "packs" / "questinggoose.vanilla.json"
DST = ROOT / "packs" / "questinggoose.nyanko.json"
MOD_PACKS = Path(r"D:\SteamLibrary\steamapps\common\Probably Stolen"
                 r"\Mods\player.dialogueblips\packs")

SAMPLE_RATE = 44100.0
KEEP_PLAIN = ("男年轻", "男老", "女年轻", "女老年", "索耶", "埃莉诺")
NYANKO_SUFFIX = "（娘化）"

SQUARE, SAW, SINE, NOISE, TRI, PINK, WHISTLE, BREAK, BITNOISE, BUZZ = 0, 1, 2, 3, 4, 5, 7, 8, 9, 11


def env_for(ms, attack, sustain):
    """反解衰减，使总时长等于 ms。时长(采样) = (a²+s²+d²)×100000"""
    need = ms / 1000 * SAMPLE_RATE / 100000
    d2 = need - attack * attack - sustain * sustain
    if d2 <= 0:
        raise ValueError(f"{ms} ms 太短，放不下 attack={attack} sustain={sustain}")
    return round(math.sqrt(d2), 4)


# ---------------------------------------------------------------- 设计表
# (角色, hz, 主体波形, 目标时长ms, attack, sustain, 参数覆盖, 附加层)
# 附加层: (hz, gain, attack, sustain, ms, 波形, 参数覆盖)
#
# 材质六族：
#   正弦  导师 305 · 卢 1308
#   方波  房东 327 · 伦警官 495 · 约翰 701
#   三角  屠夫 350 · 塞尔皮科 863 · 乔治奥 1220
#   锯齿  奥丁 375 · 亚瑟 431 · 詹姆斯 531
#   哨音  李北文 402 · 杰克逊博士 1138
#   破波  乔 462 · 胡安 569 · 勒鲁瓦 925
DESIGNS = {
    # 兜帽压深、只露紫灰眼、浅笑 → 低语。正弦没有泛音，"没有人味"；
    # 失谐只差 +4 Hz，像兜帽下有两个声音在同时说话。
    "导师": (300, SINE, 108, 0.045, 0.035,
             {"LpFilterCutoff": 0.52, "VibratoDepth": 0.06, "VibratoSpeed": 0.18,
              "Overtones": 0.06, "OvertoneFalloff": 0.62, "Slide": -0.05},
             [(304, 0.20, 0.045, 0.035, 108, SINE, {"LpFilterCutoff": 0.46}),
              (300, 0.16, 0.03, 0.05, 96, PINK, {"LpFilterCutoff": 0.45}),
              (300, 0.18, 0.01, 0.02, 22, NOISE, {"LpFilterCutoff": 0.45}),
              # 从斗篷里展示金属小物件——极轻的闪光
              (2400, 0.06, 0.003, 0.006, 9, SINE, {"LpFilterCutoff": 0.90})]),

    # 黑西装马甲、抱胸、冷脸 → 冷硬。占空比压到 0.30 让方波变薄变尖；
    # 一点气声都不给，连"人的温度"都不留。
    "房东": (318, SQUARE, 52, 0.028, 0.030,
             {"LpFilterCutoff": 0.52, "SquareDuty": 0.40, "VibratoDepth": 0.0,
              "Overtones": 0.08, "OvertoneFalloff": 0.60, "Slide": -0.07},
             [(322, 0.22, 0.022, 0.030, 46, SQUARE, {"LpFilterCutoff": 0.46, "SquareDuty": 0.34}),
              (318, 0.28, 0.008, 0.015, 18, NOISE, {"LpFilterCutoff": 0.42})]),

    # 栗发低马尾、红围裙、闭眼月牙笑、左眼旧刀疤 → 卖人肉却笑得最温柔。
    # 三角最暖、低通 0.66、轻快颤音；只留 0.03 降位——像案板的味道。
    "屠夫": (337, TRI, 96, 0.030, 0.040,
             {"LpFilterCutoff": 0.66, "VibratoDepth": 0.05, "VibratoSpeed": 0.42,
              "Overtones": 0.14, "OvertoneFalloff": 0.58, "Slide": 0.02,
              "BitCrush": 0.03},
             [(337, 0.14, 0.028, 0.045, 92, PINK, {"LpFilterCutoff": 0.52}),
              (337, 0.20, 0.008, 0.014, 20, PINK, {"LpFilterCutoff": 0.50})]),

    # 绿毛线帽 + 长红发、眉微压、坚定直视 → 坚定。
    # 锯齿给齿感与力度；零颤音 + 极小下滑，语气是"落地"的。
    # 绿毛线帽 + 长红发、耳机麦克风、手碰耳麦、眉微压 → 指挥官在通联，不是嘶吼。
    # 换掉锯齿：锯齿的谐波铺到极高，怎么压低通都留齿感。
    # 改正弦 + 失谐——只有基频，绝不可能刺耳；体量由 +4 Hz 的第二层补。
    # 威严来自"稳"（零颤音、84 ms、低通 0.48），不是来自"粗"。
    "奥丁": (357, SINE, 84, 0.025, 0.032,
             {"LpFilterCutoff": 0.48, "VibratoDepth": 0.0,
              "Overtones": 0.02, "OvertoneFalloff": 0.60, "Slide": -0.02},
             [(361, 0.30, 0.026, 0.030, 82, SINE, {"LpFilterCutoff": 0.44}),
              (357, 0.24, 0.008, 0.014, 18, NOISE, {"LpFilterCutoff": 0.44})]),
    "李北文": (378, BREAK, 68, 0.025, 0.030,
               {"LpFilterCutoff": 0.70, "VibratoDepth": 0.01,
                "Overtones": 0.14, "OvertoneFalloff": 0.54, "Slide": -0.02,
                "HpFilterCutoff": 0.10},
               [(378, 0.30, 0.008, 0.014, 18, NOISE, {"LpFilterCutoff": 0.62})]),

    # 橄榄毛线帽、颈长乱发、眉微蹙、疲惫 → 疲惫温顺。
    # 下滑 -0.07，每个字尾都在泄气；气声 0.15 把"没力气"做实。
    "亚瑟·拉弗勒": (400, SAW, 90, 0.050, 0.032,
                    {"LpFilterCutoff": 0.52, "VibratoDepth": 0.04, "VibratoSpeed": 0.20,
                     "Overtones": 0.08, "OvertoneFalloff": 0.60, "Slide": -0.07},
                    [(400, 0.15, 0.030, 0.048, 88, PINK, {"LpFilterCutoff": 0.44}),
                     (400, 0.20, 0.008, 0.014, 18, NOISE, {"LpFilterCutoff": 0.42})]),

    # 红礼帽压半边眼、精明浅笑、口袋露钞票 → 精明商人。
    # 破波是硬朗的抛物线波，比三角"有棱角"；下滑取正值 +0.06 往上挑，像在报个价。
    "乔·王尔德": (424, BREAK, 60, 0.022, 0.026,
                  {"LpFilterCutoff": 0.62, "VibratoDepth": 0.05, "VibratoSpeed": 0.50,
                   "Overtones": 0.10, "OvertoneFalloff": 0.58, "Slide": 0.06},
                  [(430, 0.16, 0.024, 0.028, 58, BREAK, {"LpFilterCutoff": 0.62}),
                   (424, 0.24, 0.008, 0.014, 18, NOISE, {"LpFilterCutoff": 0.56})]),

    # 红贝雷、墨镜压到鼻梁、心照不宣的笑 → 老练又亲昵。
    # 方波 + 占空比 0.40 = 略薄的制服感；极轻 Buzz 层（0.05）只留一丝无线电杂音。
    "伦警官": (449, SQUARE, 66, 0.025, 0.030,
               {"LpFilterCutoff": 0.60, "SquareDuty": 0.45,
                "VibratoDepth": 0.04, "VibratoSpeed": 0.30,
                "Overtones": 0.08, "OvertoneFalloff": 0.58, "Slide": -0.01},
               [(449, 0.05, 0.020, 0.024, 52, BUZZ, {"LpFilterCutoff": 0.30}),
                (449, 0.28, 0.008, 0.014, 18, NOISE, {"LpFilterCutoff": 0.50})]),

    # 偷货的小职员（无提示词，按剧情）→ 心虚。
    # 颤音快而浅（0.07@0.62）是"怕人听见"的生理反应；破波 + 降位 0.04 让她不体面。
    "胡安": (505, BREAK, 52, 0.028, 0.030,
             {"LpFilterCutoff": 0.50, "VibratoDepth": 0.07, "VibratoSpeed": 0.62,
              "Overtones": 0.06, "OvertoneFalloff": 0.60, "Slide": -0.07,
              "BitCrush": 0.04},
             [(505, 0.20, 0.008, 0.014, 16, NOISE, {"LpFilterCutoff": 0.44})]),

    # 黑眼罩、战术背心、警戒的琥珀眼 → 戒备。零气声、零颤音，
    # 下滑 -0.06 收住；她连一个多余的气息都不给你。
    "詹姆斯·贝利": (476, SAW, 62, 0.030, 0.030,
                   {"LpFilterCutoff": 0.50, "VibratoDepth": 0.0,
                    "Overtones": 0.08, "OvertoneFalloff": 0.60, "Slide": -0.06},
                   [(476, 0.26, 0.008, 0.014, 18, NOISE, {"LpFilterCutoff": 0.46})]),

    # 浅灰棕及肩直发、小侧分 → 最普通的人。
    # 方波但占空比 0.50（最标准的方波），所有参数刻意取中位——
    # "没有特征"本身成了她的特征。
    "约翰·史密斯": (535, SQUARE, 54, 0.028, 0.028,
                   {"LpFilterCutoff": 0.66, "SquareDuty": 0.50,
                    "VibratoDepth": 0.05, "VibratoSpeed": 0.40,
                    "Overtones": 0.08, "OvertoneFalloff": 0.58, "Slide": -0.08},
                   [(535, 0.20, 0.008, 0.014, 16, NOISE, {"LpFilterCutoff": 0.52})]),

    # 深蓝黑低马尾、蓝眼、温和认真、拿笔记本 → 认真新人。
    # 三角 + 偏亮低通 + 下滑取正值（+0.05），语气是"往前递"的。
    "塞尔皮科": (566, TRI, 72, 0.025, 0.030,
                {"LpFilterCutoff": 0.72, "VibratoDepth": 0.03, "VibratoSpeed": 0.35,
                 "Overtones": 0.16, "OvertoneFalloff": 0.56, "Slide": 0.08},
                [(566, 0.08, 0.022, 0.028, 66, PINK, {"LpFilterCutoff": 0.60}),
                 (566, 0.30, 0.008, 0.014, 18, NOISE, {"LpFilterCutoff": 0.56})]),

    # 歪戴的旧红贝雷、脏红制服、强撑的假笑 → 虚张声势。
    # 下滑 -0.12 全阵容最大（装出来的气势撑不住），颤音 0.10@0.55 不稳，降位 0.06。
    "勒鲁瓦": (673, BREAK, 52, 0.020, 0.024,
              {"LpFilterCutoff": 0.66, "VibratoDepth": 0.10, "VibratoSpeed": 0.55,
               "Overtones": 0.14, "OvertoneFalloff": 0.50, "Slide": -0.12,
               "BitCrush": 0.06},
              [(673, 0.28, 0.008, 0.014, 18, NOISE, {"LpFilterCutoff": 0.55})]),

    # 白毛娇小、铜框护目镜、举电路板得意展示 → 技术宅。
    # 哨音在 1138 Hz 时泛音落在 22.8 kHz（人耳之外），实际是干净正弦；
    # 加一层极轻方波（0.10）提供"电路板"的硬度。
    "杰克逊博士": (849, BREAK, 58, 0.020, 0.024,
                  {"LpFilterCutoff": 0.66, "VibratoDepth": 0.07, "VibratoSpeed": 0.55,
                   "Overtones": 0.08, "OvertoneFalloff": 0.54, "Slide": 0.03},
                  [(849, 0.10, 0.018, 0.022, 46, SQUARE, {"LpFilterCutoff": 0.58, "SquareDuty": 0.35}),
                   (849, 0.26, 0.008, 0.014, 16, NOISE, {"LpFilterCutoff": 0.58})]),

    # 金棕乱短发、虎牙笑、摊手等报价 → 元气小骗子。
    # 下滑 +0.08 上扬（讨喜的吹牛）；颤音 0.12@0.55 是跳的。
    "乔治奥": (899, TRI, 58, 0.015, 0.024,
              {"LpFilterCutoff": 0.68, "VibratoDepth": 0.12, "VibratoSpeed": 0.52,
               "Overtones": 0.10, "OvertoneFalloff": 0.55, "Slide": 0.12},
              [(899, 0.22, 0.008, 0.014, 16, NOISE, {"LpFilterCutoff": 0.62})]),

    # 金发、天蓝眼、指尖触脸颊、优雅诡异 → 优雅的诡。
    # 正弦纯净无温度 + 失谐 +6 Hz 做双声；极轻 Buzz（0.06、低通 0.30）
    # 只留金属首饰的凉意，不是噪声。长尾 100 ms，她不着急。
    "卢": (952, TRI, 100, 0.030, 0.036,
           {"LpFilterCutoff": 0.62, "VibratoDepth": 0.04, "VibratoSpeed": 0.25,
            "Overtones": 0.06, "OvertoneFalloff": 0.60, "Slide": -0.03},
           [(958, 0.28, 0.032, 0.034, 98, TRI, {"LpFilterCutoff": 0.56}),
            (952, 0.06, 0.020, 0.024, 80, BUZZ, {"LpFilterCutoff": 0.30}),
            # 「滴答，滴答」——第二下点击延迟 78 ms，一个字里响两下
            (2400, 0.11, 0.006, 0.010, 9, NOISE, {"LpFilterCutoff": 0.86}, 78),
            (952, 0.18, 0.008, 0.014, 18, NOISE, {"LpFilterCutoff": 0.50})]),
}


def build_pack(base_doc, presets):
    doc = json.loads(json.dumps(base_doc))
    doc["presets"] = presets
    doc["id"] = "questinggoose.nyanko"
    doc["name"] = "娘化音色包"
    doc["target"] = "nyanko"
    doc["replaces"] = ["questinggoose.vanilla"]
    doc["requiresMod"] = "3828971372"
    doc["version"] = "1.0.0"
    doc["note"] = ("16 位有娘化立绘且原本为男性的角色按立绘+剧情重新设计；"
                   "埃莉诺本身就是女性，与通用音色、索耶一同保留原声。"
                   "材质分六族：正弦/方波/三角/锯齿/哨音/破波。")
    return doc


def write(doc):
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    DST.write_text(text, encoding="utf-8")
    MOD_PACKS.mkdir(parents=True, exist_ok=True)
    (MOD_PACKS / DST.name).write_text(text, encoding="utf-8")


def main():
    base = json.loads(SRC.read_text(encoding="utf-8-sig"))
    base_p = base["presets"]["乔治奥"][0]["p"]
    out = {}

    for name, layers in base["presets"].items():
        if name in KEEP_PLAIN or name not in DESIGNS:
            out[name] = layers
            continue

        hz, wave, target_ms, atk, sus, over, extra = DESIGNS[name]
        built = []
        p = dict(base_p)
        p["WaveType"] = wave
        p.update(over)
        p["AttackTime"] = atk
        p["SustainTime"] = sus
        p["DecayTime"] = env_for(target_ms, atk, sus)
        built.append({"hz": hz, "gain": 1.0, "delay": 0.0, "mute": False, "p": p})

        for spec in extra:
            # 前 7 个固定，第 8 个是可选 delay(ms)——用于「滴答」这种二次点击
            e_hz, gain, e_atk, e_sus, e_ms, e_wave, e_over = spec[:7]
            delay = spec[7] if len(spec) > 7 else 0.0
            ep = dict(base_p)
            ep["WaveType"] = e_wave
            ep.update(e_over)
            ep["AttackTime"] = e_atk
            ep["SustainTime"] = e_sus
            ep["DecayTime"] = env_for(e_ms, e_atk, e_sus)
            built.append({"hz": e_hz, "gain": gain, "delay": delay, "mute": False, "p": ep})

        out[name + NYANKO_SUFFIX] = built

    write(build_pack(base, out))

    W = {0: "方波", 1: "锯齿", 2: "正弦", 4: "三角", 7: "哨音", 8: "破波"}
    print(f"[OK] {DST.name}  {DST.stat().st_size/1024:.1f} KB  {len(out)} 个预设")
    print(f"{'角色':<16}{'Hz':>6}{'材质':>6}{'层':>3}{'时长':>9}")
    rows = sorted(((n, d[0], W.get(d[1], d[1]), d[2], len(out[n + NYANKO_SUFFIX]))
                   for n, d in DESIGNS.items()), key=lambda x: x[1])
    for name, hz, mat, ms_, depth in rows:
        print(f"{name:<16}{hz:>6.0f}{mat:>6}{depth:>3}{ms_:>7} ms")
    print(f"\n已复制到 {MOD_PACKS}")
    return 0


def from_console():
    """从调音台状态回写：网页里带（娘化）的预设 → 包里去掉后缀，游戏内用原角色名。"""
    import urllib.request
    with urllib.request.urlopen("http://127.0.0.1:8731/api/state", timeout=10) as r:
        state = json.loads(r.read())["state"]

    base = json.loads(SRC.read_text(encoding="utf-8-sig"))
    out = {n: l for n, l in base["presets"].items() if n in KEEP_PLAIN}

    moved = 0
    for name, layers in (state.get("presets") or {}).items():
        if not name.endswith(NYANKO_SUFFIX):
            continue
        out[name[: -len(NYANKO_SUFFIX)]] = [
            {"hz": l["hz"], "gain": l["gain"], "delay": l["delay"], "mute": l.get("mute", False),
             "p": {k: v for k, v in l["p"].items() if k != "StartFrequency"}}
            for l in layers
        ]
        moved += 1

    write(build_pack(base, out))
    print(f"[OK] 从调音台导出 {moved} 个娘化预设 -> {DST.name}")
    return 0


if __name__ == "__main__":
    if "--from-console" in sys.argv:
        sys.exit(from_console())
    sys.exit(main())
