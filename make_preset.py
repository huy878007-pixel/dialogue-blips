"""把命名预设写进共享状态（走 /api/state 的 PUT）。

用法：
    python make_preset.py              # 写入 SPECS 里所有预设
    python make_preset.py 卢           # 只写指定预设

参数基线来自 /api/meta 的 voiceBase（= Program.Base()，31 项、不含 StartFrequency）。
音高统一走 hz，不写进 p。改动会保留其它预设和句子的现有设置。
"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8731"


def merge(*overrides):
    """在 voiceBase 上叠加，返回完整 31 项参数（保持键集合不增不减）。"""
    params = dict(VOICE_BASE)
    for block in overrides:
        params.update(block)
    return params


def layer(hz, overrides, gain=1.0, delay=0.0):
    # 只记下覆盖块，等 VOICE_BASE 从 /api/meta 取到之后再合成完整参数
    return {"hz": hz, "gain": gain, "delay": delay, "mute": False, "_over": overrides}


def build(layers):
    return [{"hz": l["hz"], "gain": l["gain"], "delay": l["delay"], "mute": l["mute"],
             "p": merge(l["_over"])} for l in layers]


# ---------------------------------------------------------------- 预设定义
# 每个角色：一句话人设 + 为什么是这些参数。依据见 音色设计_特殊NPC_2026-10-30.md
SPECS = {
    # 拾荒走私贩，第三人称自称；用户定调：友好、有趣、有点傻气但很真诚。
    # v3 依据用户「重新设计」：v2 的 140Hz 夹在房东(129)和导师(145)之间，两头只差 3-8%，
    # 在完整阵容里最容易糊。所以把音区挪进空出来的低音区(106Hz)，
    # 再用**亮度和颤动**保住"傻气"——低音 + 活泼颤音 = 热络的大个子，而不是凶。
    # v2 原值备份：140Hz / LP0.72 / atk0.03 / sus0.07 / dec0.17 / slide-0.04 /
    #              over0.14 / falloff0.60 / vib0.09@0.45 / crush0.03 / 辅音0.24
    "乔治奥": [
        layer(106, {
            "WaveType": 4, "LpFilterCutoff": 0.78,
            "AttackTime": 0.025, "SustainTime": 0.06, "DecayTime": 0.16,
            "Slide": -0.02, "Overtones": 0.18, "OvertoneFalloff": 0.55,
            "VibratoDepth": 0.13, "VibratoSpeed": 0.50, "BitCrush": 0.02,
        }),
        # 辅音层：仍然轻，他不用力说话
        layer(106, {
            "WaveType": 3, "LpFilterCutoff": 0.58,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.06,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.24),
    ],

    # 恶作剧式恐怖反派：在你东西里藏炸弹，"小营养果"，咯咯笑。
    # v2 依据用户反馈「太刺耳，要更优雅的诡味」：
    #   刺耳来自高音区 + 金属 buzz + 快颤音 —— 那是恐怖片的手法，不是优雅。
    #   改成：音区降到 590、去掉降位、低通压暗、颤音放慢放浅、尾巴拉长，
    #   不安感改由「轻微失谐的双声」承担（两条差 6 Hz 的三角波）。
    #   金属层只留一丝（0.09，且通到很暗），够"不对劲"，不刮耳朵。
    # 社区 wiki 特意提醒「卢不是伦警官」，所以仍需和伦警官(118Hz)拉开约 5 倍。
    "卢": [
        # 主体：暗一点、慢起音、长尾 —— 从容
        layer(590, {
            "WaveType": 4, "LpFilterCutoff": 0.60,
            "AttackTime": 0.04, "SustainTime": 0.08, "DecayTime": 0.21,
            "Slide": -0.04, "Overtones": 0.10, "OvertoneFalloff": 0.65,
            "VibratoDepth": 0.05, "VibratoSpeed": 0.25, "BitCrush": 0,
        }),
        # 失谐层：差 6 Hz 的第二条三角波。两个几乎同频的声音 = 说不出的怪。
        layer(596, {
            "WaveType": 4, "LpFilterCutoff": 0.55,
            "AttackTime": 0.05, "SustainTime": 0.07, "DecayTime": 0.20,
            "Slide": -0.05, "Overtones": 0.08, "OvertoneFalloff": 0.65,
        }, gain=0.30),
        # 金属层：极轻且压得很暗，只留一丝
        layer(590, {
            "WaveType": 11, "LpFilterCutoff": 0.35,
            "AttackTime": 0.02, "SustainTime": 0.03, "DecayTime": 0.10,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.09),
    ],

    # 埃莉诺 —— 女声，上层贵族，高傲（用户 2026-10-30 明确要求）。
    # v2 纠正了 v1 的方向：v1 做成了「委屈」（长尾 + 叹气下滑 + 气声 0.14），
    # 那是她落魄之后的样子；高傲的贵族是「干、准、不拖泥带水」。
    #   女声    -> 720Hz（明显是女的，但远离 1056 那种甜）
    #   高傲    -> 尾巴从 0.19 收到 0.14（短促＝不耐烦）、起音利落 0.025
    #   贵族    -> 气声砍到 0.08（气息＝亲近感，高贵的人不给你这个）、吐字清楚 0.22
    #   清楚    -> 低通 0.75、泛音 0.10（偏薄偏亮，不是厚暖）
    #   不屑    -> 尾音只留很小的下滑 -0.06
    "埃莉诺": [
        layer(720, {
            "WaveType": 4, "LpFilterCutoff": 0.75,
            "AttackTime": 0.025, "SustainTime": 0.05, "DecayTime": 0.14,
            "Slide": -0.06, "Overtones": 0.10, "OvertoneFalloff": 0.60,
            "VibratoDepth": 0.03, "VibratoSpeed": 0.30, "BitCrush": 0,
        }),
        # 气声层：只留一点点，是"清楚"而不是"温柔"
        layer(720, {
            "WaveType": 5, "LpFilterCutoff": 0.55,
            "AttackTime": 0.02, "SustainTime": 0.03, "DecayTime": 0.10,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.08),
        # 辅音层：吐字利落
        layer(720, {
            "WaveType": 3, "LpFilterCutoff": 0.55,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.05,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.22),
    ],

    # 伦警官 —— 治安部，冷面执法，私下把捡到的东西卖给你。
    # 台词：「别慌，只是例行检查」「来都来了，顺手给我拿点止痛药吧」
    #       「嘿，我……呃……捡到了一些东西」「你买吗？」（私下交易那面）
    # 设计：
    #   冷面   -> 118Hz 成年男、无颤音（不动摇）、尾巴短（不闲聊）
    #   官腔   -> 低通压到 0.50（闷、不亲切）
    #   干     -> 不加气声（气息＝亲近感，他不给你）
    #   硬     -> 辅音层 0.30，起音利落
    #   不油   -> 不加毛刺、不加失谐；他和卢/乔治奥都不是一类
    # 他也是卢的对照组：118Hz vs 711Hz，差 6 倍。
    "伦警官": [
        layer(118, {
            "WaveType": 4, "LpFilterCutoff": 0.50,
            "AttackTime": 0.03, "SustainTime": 0.06, "DecayTime": 0.16,
            "Slide": -0.05, "Overtones": 0.08, "OvertoneFalloff": 0.60,
            "VibratoDepth": 0, "VibratoSpeed": 0.30, "BitCrush": 0,
        }),
        # 辅音层：硬起音，像在念公事
        layer(118, {
            "WaveType": 3, "LpFilterCutoff": 0.45,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.05,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.30),
    ],

    # 塞尔皮科 —— 实习警员，下层区出身，热血理想主义，后来幻灭。
    # 台词：「维护空间站的安全一直是我的梦想」「你这里有零食吗？我想拿去跟新同事们搞好关系」
    #       「天呐，我真得整两杯了」「没想到竟然烂成了这样」
    # 只做他刚出场（热血）这一版。
    # 设计：
    #   年轻   -> 195Hz（比乔治奥 140 高、比 118 的伦警官高一大截，一听就是小伙子）
    #   热血   -> 起音快、低通 0.74 亮、泛音 0.16 有劲
    #   有情绪 -> 颤音 0.06（不像伦警官那样平）
    #   话多   -> 尾巴 79ms，比伦警官长
    #   对照   -> 和伦警官同一建制但完全不同：一个 118Hz 干冷，一个 195Hz 热心
    "塞尔皮科": [
        layer(195, {
            "WaveType": 4, "LpFilterCutoff": 0.74,
            "AttackTime": 0.03, "SustainTime": 0.07, "DecayTime": 0.17,
            "Slide": -0.08, "Overtones": 0.16, "OvertoneFalloff": 0.58,
            "VibratoDepth": 0.06, "VibratoSpeed": 0.40, "BitCrush": 0,
        }),
        # 辅音层：吐字清楚有劲
        layer(195, {
            "WaveType": 3, "LpFilterCutoff": 0.55,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.05,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.28),
    ],

    # 导师 —— 教程引导。"听好了，菜鸟""我一直在看着，你做得很不错"
    # v2 依据用户反馈「太低沉了」。原版 97Hz 落在低音区和伦警官/房东/乔治奥挤成一团。
    # 改法：不靠低音表现"老"，改用**慢速深颤音 + 气声 + 慢包络**——
    # 老年嗓音的真实特征是不稳和慢，不是音低。音区抬到 150Hz。
    "导师": [
        layer(150, {
            "WaveType": 4, "LpFilterCutoff": 0.64,
            "AttackTime": 0.055, "SustainTime": 0.08, "DecayTime": 0.19,
            "Slide": -0.06, "Overtones": 0.14, "OvertoneFalloff": 0.58,
            "VibratoDepth": 0.10, "VibratoSpeed": 0.20, "BitCrush": 0,
        }),
        layer(150, {   # 气声：年龄，比原来轻
            "WaveType": 5, "LpFilterCutoff": 0.50,
            "AttackTime": 0.03, "SustainTime": 0.05, "DecayTime": 0.14,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.09),
        layer(150, {
            "WaveType": 3, "LpFilterCutoff": 0.48,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.05,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.24),
    ],

    # 房东 —— 催租。"你好啊，有钱交租吗？""岂有此理！"被买断后："真了不起。"
    # 强硬、直接、认赌服输。低音区 + 无颤音 + 极短尾巴（堵门口不走的债主）。
    # 注意：130Hz 和乔治奥 140Hz 只差 7%，靠"暗+短+失谐 对 亮+长+颤音"拉开。
    "房东": [
        layer(130, {
            "WaveType": 4, "LpFilterCutoff": 0.50,
            "AttackTime": 0.02, "SustainTime": 0.05, "DecayTime": 0.13,
            "Slide": -0.04, "Overtones": 0.10, "OvertoneFalloff": 0.60,
            "VibratoDepth": 0, "VibratoSpeed": 0.30, "BitCrush": 0,
        }),
        layer(134, {   # 失谐：体量，他不是瘦小的人
            "WaveType": 4, "LpFilterCutoff": 0.45,
            "AttackTime": 0.03, "SustainTime": 0.04, "DecayTime": 0.12,
            "Slide": -0.04, "Overtones": 0.08, "OvertoneFalloff": 0.60,
        }, gain=0.22),
        layer(130, {   # 辅音：很硬
            "WaveType": 3, "LpFilterCutoff": 0.45,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.05,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.28),
    ],

    # 索耶 —— 下层区清道夫，介绍付费清洁与地下交易所；也接"解决麻烦"的活。
    # 台词：「我小时候流落街头，是老爷子给了我饭吃」/「不如你出信用点，我们帮你把这个麻烦解决掉？」
    # 设计重点：语气越温和，事情越不温和。所以干净、平、不用力——反差本身就是设计。
    "索耶": [
        layer(162, {
            "WaveType": 4, "LpFilterCutoff": 0.58,
            "AttackTime": 0.04, "SustainTime": 0.07, "DecayTime": 0.17,
            "Slide": -0.06, "Overtones": 0.10, "OvertoneFalloff": 0.60,
            "VibratoDepth": 0.03, "VibratoSpeed": 0.30, "BitCrush": 0,
        }),
        layer(162, {
            "WaveType": 5, "LpFilterCutoff": 0.50,
            "AttackTime": 0.02, "SustainTime": 0.04, "DecayTime": 0.12,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.08),
        layer(162, {
            "WaveType": 3, "LpFilterCutoff": 0.50,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.05,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.24),
    ],

    # 乔·王尔德 —— 不是"卖保险的"，是**街头办事员/中间人**。
    # 台词证据：地契过户「这地方现在归你了，恭喜」「你认识一个专门的人，能处理那些手续」
    #           「要弄好那些手续，每一步都盯得很紧」「准备好了就给我打电话」
    #           网络引入「网络是个生态系统」「只知道一味榨取、没有任何规矩的话，平衡就会被打破」
    # 用户定调：精明的街头办公人员。
    # 设计：
    #   精明   -> 说快、说短（68ms）、吐字极清楚（辅音 0.28）、没有拖腔（下滑只 -0.02）
    #   办公   -> 干（气声 0.05）、亮而清（低通 0.74）、无颤音（不动摇）
    #   办事员 -> 泛音 0.18 让声音"实"，像人在算账而不是在表演
    #   街头   -> 一层极轻失谐 0.15（不是乔治奥那种油，是"多一个心眼"）
    # 和乔治奥（140Hz 油滑友善）、伦警官（118Hz 冷硬）彻底分开：255Hz 中高、快、干。
    "乔·王尔德": [
        layer(255, {
            "WaveType": 4, "LpFilterCutoff": 0.74,
            "AttackTime": 0.025, "SustainTime": 0.06, "DecayTime": 0.16,
            "Slide": -0.02, "Overtones": 0.18, "OvertoneFalloff": 0.55,
            "VibratoDepth": 0.03, "VibratoSpeed": 0.30, "BitCrush": 0,
        }),
        layer(258, {   # 极轻失谐：多一个心眼
            "WaveType": 4, "LpFilterCutoff": 0.65,
            "AttackTime": 0.03, "SustainTime": 0.05, "DecayTime": 0.15,
            "Slide": -0.02, "Overtones": 0.10, "OvertoneFalloff": 0.58,
        }, gain=0.15),
        layer(255, {   # 辅音：算账的人吐字最清楚
            "WaveType": 3, "LpFilterCutoff": 0.60,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.05,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.28),
    ],

    # 杰克逊博士 —— 卖设备与模组、储物和机器区扩容。
    # 理性、清楚、"说明书成精"。中高音区、亮、泛音丰富、无气声。
    "杰克逊博士": [
        layer(320, {
            "WaveType": 4, "LpFilterCutoff": 0.78,
            "AttackTime": 0.03, "SustainTime": 0.05, "DecayTime": 0.15,
            "Slide": -0.04, "Overtones": 0.20, "OvertoneFalloff": 0.55,
            "VibratoDepth": 0.02, "VibratoSpeed": 0.30, "BitCrush": 0,
        }),
        layer(320, {
            "WaveType": 3, "LpFilterCutoff": 0.60,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.05,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.22),
    ],

    # 屠夫 —— 通缉犯，供肉；举报后会报复，索耶因此介入。
    # 用户 2026-10-30 透露：**他卖的是人肉**。
    # 曾据此起草过 v2「正常得可怕」（96Hz / 低通0.64 / 68ms / 无颤音 / 毛刺0.10），
    # 但用户听完 v1 后说「设计非常不错，不用改」——**定稿是 v1**，本文件与之保持一致。
    # v1 的设计：沉重、慢、量大。不用"听起来危险"，他本来就危险。
    #   音区 90Hz  —— 全阵容最低（乔治奥 106 是次低），一听就是另一个量级
    #   低通 0.48  —— 厚、暗、不透
    #   起音 0.05 + 尾 0.22 —— 慢而长（130ms），不急着说话
    #   失谐 0.28  —— 体量
    #   毛刺 0.08  —— 本行是切肉，声音不干净
    "屠夫": [
        layer(90, {
            "WaveType": 4, "LpFilterCutoff": 0.48,
            "AttackTime": 0.05, "SustainTime": 0.08, "DecayTime": 0.22,
            "Slide": -0.03, "Overtones": 0.16, "OvertoneFalloff": 0.55,
            "VibratoDepth": 0.02, "VibratoSpeed": 0.25, "BitCrush": 0.08,
        }),
        layer(93, {   # 失谐：体量
            "WaveType": 4, "LpFilterCutoff": 0.44,
            "AttackTime": 0.06, "SustainTime": 0.07, "DecayTime": 0.21,
            "Slide": -0.03, "Overtones": 0.12, "OvertoneFalloff": 0.55,
        }, gain=0.28),
        layer(90, {   # 辅音：硬
            "WaveType": 3, "LpFilterCutoff": 0.42,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.06,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.30),
    ],

    # 奥丁·哈拉尔德森 —— 通缉4。军阀/组织头目。
    # 台词：「别按报警器。」「我有一项商业提议要和你谈谈。」
    #       「我的人需要一些物资：枪支、弹药、护甲、毒药、物资箱和通行卡」
    #       「举报我，你就再也见不到我了。」「你会后悔的。」
    # 全阵容最低音、最慢、零颤音——有气场的人不需要提高嗓门。
    "奥丁": [
        layer(78, {
            "WaveType": 4, "LpFilterCutoff": 0.46,
            "AttackTime": 0.05, "SustainTime": 0.09, "DecayTime": 0.24,
            "Slide": -0.02, "Overtones": 0.14, "OvertoneFalloff": 0.55,
            "VibratoDepth": 0, "VibratoSpeed": 0.25, "BitCrush": 0.02,
        }),
        layer(80, {   # 失谐：体量
            "WaveType": 4, "LpFilterCutoff": 0.42,
            "AttackTime": 0.06, "SustainTime": 0.08, "DecayTime": 0.23,
            "Slide": -0.02, "Overtones": 0.10, "OvertoneFalloff": 0.55,
        }, gain=0.26),
        layer(78, {
            "WaveType": 3, "LpFilterCutoff": 0.42,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.06,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.26),
    ],

    # 胡安 —— 通缉7。**不是街边小贩**：他是政府开的食品店员工，把店里的货偷出来倒卖。
    # 台词：「我有些多余的食物要卖。你要是愿意收，以后我还能弄到更多。」
    #       「我保证，以后还能一直给你带便宜的吃的。」
    # 所以是"鬼鬼祟祟的小职员"，不是"热情的大叔"：
    #   音区 180Hz   —— 普通男性职员，不高不低
    #   低通 0.52    —— 闷，是柜台后面的声音，不是街上的
    #   起音 0.03 / 尾 0.14 —— 短促（怕人听见）
    #   颤音 0.07/速度0.60 —— 快而浅的抖 = 心虚
    #   泛音 0.08    —— 薄，没有热情
    #   毛刺 0.04    —— 一点点不体面
    "胡安": [
        layer(180, {
            "WaveType": 4, "LpFilterCutoff": 0.52,
            "AttackTime": 0.03, "SustainTime": 0.05, "DecayTime": 0.14,
            "Slide": -0.09, "Overtones": 0.08, "OvertoneFalloff": 0.60,
            "VibratoDepth": 0.07, "VibratoSpeed": 0.60, "BitCrush": 0.04,
        }),
        layer(180, {
            "WaveType": 3, "LpFilterCutoff": 0.45,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.05,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.24),
    ],

    # 亚瑟·拉弗勒 —— 通缉3。前革命军，只想买吃的，求饶时还想摆点旧资历。
    # 台词：「我需要买些食物和材料。」「我早就跟革命军没多大关系了。」
    #       「你要是放我走，我就在革命军的年轻人面前替你美言几句。」
    # 设计：疲惫、暗、慢、有气声——落魄但有教养，不是街头混混。
    "亚瑟·拉弗勒": [
        layer(215, {
            "WaveType": 4, "LpFilterCutoff": 0.52,
            "AttackTime": 0.05, "SustainTime": 0.06, "DecayTime": 0.18,
            "Slide": -0.09, "Overtones": 0.10, "OvertoneFalloff": 0.60,
            "VibratoDepth": 0.05, "VibratoSpeed": 0.25, "BitCrush": 0,
        }),
        layer(215, {   # 气声：落魄
            "WaveType": 5, "LpFilterCutoff": 0.45,
            "AttackTime": 0.03, "SustainTime": 0.04, "DecayTime": 0.14,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.13),
        layer(215, {
            "WaveType": 3, "LpFilterCutoff": 0.45,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.05,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.22),
    ],

    # 詹姆斯·贝利 —— 通缉1。偷治安部装备倒卖，圆滑、讲生意、怕事。
    # 台词：「我有些多余的装备，自己用不上。有看上的吗？」「全要的话，我给你打六七折。」
    #       「你不举报我的话，我可以一直给你送治安部的装备。」被围时：「妈的。」
    "詹姆斯·贝利": [
        layer(235, {
            "WaveType": 4, "LpFilterCutoff": 0.70,
            "AttackTime": 0.03, "SustainTime": 0.06, "DecayTime": 0.15,
            "Slide": -0.08, "Overtones": 0.14, "OvertoneFalloff": 0.58,
            "VibratoDepth": 0.07, "VibratoSpeed": 0.40, "BitCrush": 0.03,
        }),
        layer(235, {
            "WaveType": 3, "LpFilterCutoff": 0.54,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.05,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.26),
    ],

    # 约翰·史密斯 —— 通缉8。名字太常见被治安部反复误抓，最终刷漆报复。
    # 台词：「因为我的名字太常见，治安部那边把人搞混了。」「这个月他们都抓我四回了！！」
    #       「早啊！新刷的漆喜欢吗？这就是你无缘无故举报我的下场。」
    # 设计：普通到不能再普通的男声，略带委屈的偏高；短促、有点急。
    "约翰·史密斯": [
        layer(290, {
            "WaveType": 4, "LpFilterCutoff": 0.68,
            "AttackTime": 0.025, "SustainTime": 0.05, "DecayTime": 0.14,
            "Slide": -0.10, "Overtones": 0.12, "OvertoneFalloff": 0.58,
            "VibratoDepth": 0.08, "VibratoSpeed": 0.45, "BitCrush": 0,
        }),
        layer(290, {
            "WaveType": 3, "LpFilterCutoff": 0.52,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.05,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.24),
    ],

    # 李北文 —— 通缉6。被冤枉的药剂师，研发不成瘾止痛药。
    # 用户要求：**更学者一些**，且他东亚面孔，**偏中性音**。
    # 学者 = 平、准、不带情绪、语速稳；中性 = 抬音区 + 减掉低频泛音（不做"厚男人声"）
    #   音区 365Hz   —— 抬到中性区，和 312 的博士、409→430 的勒鲁瓦都拉开
    #   低通 0.80    —— 清亮、清楚，念数据的那种清楚
    #   下滑 -0.02   —— 几乎不拖腔，不带任何推销感或情绪
    #   颤音 0.01    —— 几乎没有。这是"克制"的参数
    #   泛音 0.22/衰减0.52 —— 薄而清晰，不暖
    #   辅音 0.34    —— 全阵容最重：说话极其仔细
    #   尾 0.18      —— 90ms，比一般人长一点 = 说话有分寸，不抢
    "李北文": [
        layer(365, {
            "WaveType": 4, "LpFilterCutoff": 0.80,
            "AttackTime": 0.03, "SustainTime": 0.07, "DecayTime": 0.18,
            "Slide": -0.02, "Overtones": 0.22, "OvertoneFalloff": 0.52,
            "VibratoDepth": 0.01, "VibratoSpeed": 0.30, "BitCrush": 0,
        }),
        layer(365, {
            "WaveType": 3, "LpFilterCutoff": 0.62,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.05,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.34),
    ],

    # 勒鲁瓦 —— 通缉9。冒充治安人员被抓。
    # 用户定调：**装腔作势的傻逼**——不是真有底气，是在"表演有底气"。
    # 所以不能做沉稳，要做**虚张声势**：
    #   音区 430Hz   —— 偏高。把自己当回事的人往往声音不低
    #   起音 0.02    —— 冲，抢话
    #   尾 0.13      —— 52ms，最急促之一
    #   下滑 -0.12   —— 全阵容最大下滑 = 装了底气但撑不住
    #   颤音 0.12/速度0.55 —— **不稳的抖**，装出来的气势会漏
    #   泛音 0.20/衰减0.50 —— 亮而毛躁
    #   毛刺 0.06    —— 便宜、不体面
    "勒鲁瓦": [
        layer(430, {
            "WaveType": 4, "LpFilterCutoff": 0.70,
            "AttackTime": 0.02, "SustainTime": 0.05, "DecayTime": 0.13,
            "Slide": -0.12, "Overtones": 0.20, "OvertoneFalloff": 0.50,
            "VibratoDepth": 0.12, "VibratoSpeed": 0.55, "BitCrush": 0.06,
        }),
        layer(430, {
            "WaveType": 3, "LpFilterCutoff": 0.55,
            "AttackTime": 0.01, "SustainTime": 0.02, "DecayTime": 0.05,
            "Slide": 0, "Overtones": 0, "OvertoneFalloff": 0,
        }, gain=0.30),
    ],
}


def call(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def main():
    global VOICE_BASE
    # 保护：默认不覆盖已存在的预设。
    # 用户在面板里手动调过的东西比这里的种子值更重要 —— 想覆盖必须显式 --force。
    force = "--force" in sys.argv
    wanted = [a for a in sys.argv[1:] if not a.startswith("--")] or list(SPECS)

    status, meta = call("GET", "/api/meta")
    if status != 200:
        print("读 meta 失败", meta)
        return 1
    VOICE_BASE = meta["voiceBase"]
    if "StartFrequency" in VOICE_BASE:
        print("voiceBase 不该带 StartFrequency")
        return 1

    for name in wanted:
        if name not in SPECS:
            print(f"没有叫 {name} 的预设")
            return 1
        for attempt in range(5):
            status, snap = call("GET", "/api/state")
            if status != 200:
                print("读 state 失败", snap)
                return 1
            state = snap["state"]
            presets = dict(state.get("presets") or {})
            if name in presets and not force:
                print(f"跳过 {name}：面板里已经有这个预设了（用户可能手动调过）。要覆盖加 --force")
                break
            built = build(SPECS[name])
            presets[name] = built
            state["presets"] = presets
            state["layers"] = built
            state["selectedPreset"] = name
            status, body = call("PUT", "/api/state", {
                "baseRevision": snap["revision"], "source": "assistant", "state": state})
            if status == 200:
                print(f"OK {name}: rev={body['revision']} layers={len(body['state']['layers'])} "
                      f"presets={len(body['state']['presets'])}")
                break
            print(f"  {name} 重试 {attempt+1}: HTTP {status}")
        else:
            print(f"写入 {name} 失败")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
