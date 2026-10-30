using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;

/// <summary>
/// 游戏内控制面板（F11）——还原调音台的分级结构：
///
///   一级  角色（预设）      &lt; 乔治奥 &gt;
///   二级  层               &lt; 第 2 层 · 三角波 &gt;
///   三级  参数分级          基础 / 进阶 / 高阶  → 具体滑条
///
/// 参数表与分组**照抄调音台 panel.html 的 PARAMETER_TIERS**，保证两边一致。
/// 视觉复用游戏自己的预制体：CustomUIManager.optionUIPrefab，层级 meta/menu 同 ModConfigWindow。
/// 改动停手 0.6 秒自动写 overrides.json。
/// </summary>
internal static class Panel
{
    const string Id = "dialogueblips:panel";
    const string Tag = "[DialogueBlips]";

    const float FONT_SCALE = 0.85f;
    const float SECTION_GAP = 12f;
    const int SEPARATOR_PADDING = 2;
    const float ROW_SPACING = 4f;
    const float AUTO_SAVE_DELAY = 0.6f;

    // ---------------------------------------------------------------- 参数表（同调音台）
    /// <summary>(slot, 标签, 最小, 最大, 整数)</summary>
    static readonly (string slot, string label, float min, float max, bool whole)[] BasicParams =
    {
        ("hz",             "音高 Hz",      40f,  3000f, true),
        ("gain",           "层音量",       0f,   1.5f,  false),
        ("AttackTime",     "起音",         0f,   1f,    false),
        ("SustainTime",    "持续",         0f,   1f,    false),
        ("DecayTime",      "衰减",         0f,   1f,    false),
        ("LpFilterCutoff", "明亮度（低通）", 0f,  1f,    false),
    };

    static readonly (string slot, string label, float min, float max, bool whole)[] IntermediateParams =
    {
        ("Slide",              "滑音",       -1f, 1f, false),
        ("VibratoDepth",       "颤音幅度",    0f,  1f, false),
        ("VibratoSpeed",       "颤音速度",    0f,  1f, false),
        ("Overtones",          "泛音数",      0f,  1f, false),
        ("OvertoneFalloff",    "泛音衰减",    0f,  1f, false),
        ("SustainPunch",       "冲击",        0f,  1f, false),
        ("CompressionAmount",  "压缩",        0f,  1f, false),
        ("BitCrush",           "降位粗糙度",  0f,  1f, false),
        ("LpFilterResonance",  "低通共振",    0f,  1f, false),
        ("HpFilterCutoff",     "高通",        0f,  1f, false),
    };

    static readonly (string slot, string label, float min, float max, bool whole)[] AdvancedParams =
    {
        ("MasterVolume",       "合成器音量",   0f,  1f, false),
        ("MinFrequency",       "最低频率",     0f,  1f, false),
        ("SquareDuty",         "方波占空",     0f,  1f, false),
        ("DeltaSlide",         "滑音加速",    -1f,  1f, false),
        ("DutySweep",          "占空扫描",    -1f,  1f, false),
        ("ChangeAmount",       "变调幅度",    -1f,  1f, false),
        ("ChangeSpeed",        "变调速度",     0f,  1f, false),
        ("ChangeRepeat",       "变调重复",     0f,  1f, false),
        ("ChangeAmount2",      "变调幅度2",   -1f,  1f, false),
        ("ChangeSpeed2",       "变调速度2",    0f,  1f, false),
        ("RepeatSpeed",        "重复速度",     0f,  1f, false),
        ("FlangerOffset",      "镶边偏移",    -1f,  1f, false),
        ("FlangerSweep",       "镶边扫描",    -1f,  1f, false),
        ("LpFilterCutoffSweep", "低通扫描",   -1f,  1f, false),
        ("HpFilterCutoffSweep", "高通扫描",   -1f,  1f, false),
        ("BitCrushSweep",      "降位扫描",    -1f,  1f, false),
        ("delay",              "层延迟 ms",    0f,  120f, true),
    };

    static readonly string[] Tiers = { "基础", "进阶", "高阶" };
    static readonly string[] WaveNames =
    {
        "方波", "锯齿", "正弦", "噪声", "三角", "粉噪", "正切",
        "哨音", "破碎波", "位噪声", "组合波", "蜂鸣",
    };

    static int activeTier;

    /// <summary>每级参数的行容器。整行隐藏——只隐藏滑条会留下孤零零的标签。</summary>
    static readonly List<RectTransform>[] tierRows = { new List<RectTransform>(), new List<RectTransform>(), new List<RectTransform>() };

    static CustomUIWindow window;
    public static bool IsOpen => window != null && window.IsAlive && window.IsVisible;
    static AudioSource audition;
    static string selected;
    static int charIndex;
    static int layerIndex;
    static float lastAudition;
    static bool suppress;

    static bool dirty;
    static float dirtyAt;
    static string packName = "";

    static List<(string zh, string preset, string tier)> cast = new List<(string, string, string)>();

    // ---------------------------------------------------------------- 开关
    public static void Toggle()
    {
        try
        {
            if (window != null && window.IsAlive)
            {
                if (window.IsVisible) window.Close();
                else { RefreshBank(); window.Show(); }
                return;
            }
            Open();
        }
        catch (Exception e)
        {
            Debug.LogError($"{Tag} 面板打开失败：{e}");
        }
    }

    public static void Tick()
    {
        if (!dirty || Time.unscaledTime - dirtyAt < AUTO_SAVE_DELAY) return;
        SaveIfNeeded();
        dirtyAt = Time.unscaledTime;
        PublishFocus();
    }

    public static void SaveIfNeeded()
    {
        if (!VoiceBank.Ready) return;
        if (VoiceBank.SaveOverrides(PersonaResolver.Folder)) dirty = false;
        else
        {
            dirty = true;
            window?.Get("status")?.SetText("保存失败，改动仍在内存，将重试；请检查目录写入权限");
        }
    }

    public static void NoteSpeaker(string preset)
    {
        if (window == null || !window.IsAlive) return;
        window.Get("now")?.SetText(string.IsNullOrEmpty(preset) ? "正在说话：—" : $"正在说话：{preset}");
    }

    // ---------------------------------------------------------------- 构建
    static void Open()
    {
        DialogueBlipsMod.ReapplyAudio();
        var manager = CustomUIManager.Instance;
        if (manager == null)
        {
            Debug.LogWarning($"{Tag} 当前场景没有 CustomUIManager，开不了面板");
            return;
        }
        var inStore = StoreUIManager.Instance != null;
        var b = manager.CreateWindow(Id, "对话音效", inStore ? "meta" : "menu", manager.optionUIPrefab)
                       .SetCloseOnEscape(!inStore)
                       .SetDraggable(true)
                       .OnClose(SaveIfNeeded);
        foreach (var rows in tierRows) rows.Clear();
        b.BeginScrollFlexible();

        b.AddLabel(VoiceBank.Ready
            ? $"生效：{VoiceBank.ActiveDisplayName} · 预设 {VoiceBank.PresetCount} 个"
            : "没读到预设包，把 .json 放进音色包文件夹后点「重新扫描」", "status");
        Shrink(b);
        b.AddLabel("正在说话：—", "now");
        Shrink(b);
        b.AddSpace(SECTION_GAP);

        // ── 音量（原模组配置窗口的三项，全部搬到面板）──
        Section(b, "音量与节奏");
        AudioSlider(b, "人物对话音效音量", DialogueBlipsMod.VolumeGain, 0f, DialogueBlipsMod.GainLimit, "vol_voice");
        AudioSlider(b, "打字机音效音量", DialogueBlipsMod.NativeVolume, 0f, 1f, "vol_native");
        AudioSliderInt(b, "最短发声间隔 (ms)", DialogueBlipsMod.ThrottleMs, 20, 200, "vol_throttle");
        b.AddSpace(SECTION_GAP);

        // ── 一级：音色包 ──
        Section(b, "音色包");
        if (VoiceBank.Ready)
        {
            var labels = PackLabels();
            b.BeginRow(ROW_SPACING, TextAnchor.MiddleLeft);
            b.AddDropdown(labels, Mathf.Max(0, labels.IndexOf(VoiceBank.ActiveDisplayName)), SwitchPack, "packsel");
            Shrink(b);
            b.End();
        }
        b.BeginRow(ROW_SPACING, TextAnchor.MiddleLeft);
        b.AddButton("＋ 添加音色包…", ShowPacksFolder).WithTooltip("打开音色包文件夹");
        Shrink(b);
        b.AddButton("重新扫描", Rescan).WithTooltip("丢进新文件后不用重启游戏");
        Shrink(b);
        b.End();
        b.AddSpace(SECTION_GAP);

        // ── 一级：角色 ──
        Section(b, "角色与全部预设");
        RebuildCast();
        if (cast.Count == 0)
        {
            b.AddLabel("人物表没载入", "curname");
            Shrink(b);
        }
        else
        {
            b.BeginRow(ROW_SPACING, TextAnchor.MiddleCenter);
            b.AddButton("<", () => StepChar(-1));
            Shrink(b);
            b.AddLabel("—", "curname");
            Shrink(b);
            b.AddButton(">", () => StepChar(1));
            Shrink(b);
            b.End();
        }
        b.AddSpace(SECTION_GAP * 0.66f);

        // ── 二级：层 ──
        Section(b, "层");
        b.BeginRow(ROW_SPACING, TextAnchor.MiddleCenter);
        b.AddButton("<", () => StepLayer(-1));
        Shrink(b);
        b.AddLabel("—", "layername");
        Shrink(b);
        b.AddButton(">", () => StepLayer(1));
        Shrink(b);
        b.End();
        b.BeginRow(ROW_SPACING, TextAnchor.MiddleCenter);
        b.AddButton("＋ 加一层", AddLayer).WithTooltip("复制最后一层并降一半音量");
        Shrink(b);
        b.AddButton("－ 删层", RemoveLayer).WithTooltip("至少保留一层");
        Shrink(b);
        b.End();
        b.AddSpace(SECTION_GAP * 0.66f);

        // ── 三级：参数分级 ──
        Section(b, "参数");
        b.BeginRow(ROW_SPACING, TextAnchor.MiddleCenter);
        for (var tier = 0; tier < Tiers.Length; tier++)
        {
            var captured = tier;
            b.AddButton(Tiers[tier], () => SetTier(captured), "tier" + tier);
            Shrink(b);
        }
        b.End();

        AddTierRows(b, 0, BasicParams);
        AddTierRows(b, 1, IntermediateParams);
        AddWaveRow(b);
        AddTierRows(b, 2, AdvancedParams);
        b.AddSpace(SECTION_GAP);

        // ── 导出 ──
        Section(b, "另存为新的音色包");
        b.BeginRow(ROW_SPACING, TextAnchor.MiddleLeft);
        b.AddLabel("包名");
        Shrink(b);
        packName = string.IsNullOrEmpty(packName) ? VoiceBank.ActiveDisplayName + " 自定义" : packName;
        b.AddInput("音色包名称", packName, value => packName = value, "packname");
        Shrink(b);
        b.End();
        b.BeginRow(0f, TextAnchor.MiddleCenter);
        b.AddButton("导出当前音色包", Export);
        Shrink(b);
        b.AddButton("保存改动", SaveIfNeeded);
        Shrink(b);
        b.End();
        b.End();

        window = b.Show();
        SetTier(activeTier);
        if (cast.Count > 0) SelectChar(charIndex);
        Debug.Log($"{Tag} 面板已打开：{cast.Count} 个角色，{VoiceBank.PresetCount} 个预设");
    }

    /// <summary>全局音量滑条：写进模组配置（ConfigEntry.Set 会自己保存），并立刻生效。</summary>
    static void AudioSlider(CustomUIBuilder b, string label, ConfigEntry<float> entry,
        float min, float max, string id)
    {
        if (entry == null) return;
        b.BeginRow(ROW_SPACING, TextAnchor.MiddleLeft);
        b.AddLabel(label);
        Shrink(b);
        b.AddSlider(min, max, Mathf.Clamp(entry.Value, min, max), value =>
        {
            entry.Set(value);
            DialogueBlipsMod.ReapplyAudio();
            window?.Get("v_" + id)?.SetText(Fmt(entry.Value, false));
        }, false, id);
        Shrink(b)?.SetFixedWidth(224f);
        b.AddLabel(Fmt(Mathf.Clamp(entry.Value, min, max), false), "v_" + id);
        Shrink(b)?.SetFixedWidth(64f);
        b.End();
    }

    static void AudioSliderInt(CustomUIBuilder b, string label, ConfigEntry<int> entry,
        int min, int max, string id)
    {
        if (entry == null) return;
        b.BeginRow(ROW_SPACING, TextAnchor.MiddleLeft);
        b.AddLabel(label);
        Shrink(b);
        b.AddSlider(min, max, Mathf.Clamp(entry.Value, min, max), value =>
        {
            entry.Set(Mathf.RoundToInt(value));
            window?.Get("v_" + id)?.SetText(Fmt(value, true));
        }, true, id);
        Shrink(b)?.SetFixedWidth(224f);
        b.AddLabel(Fmt(entry.Value, true), "v_" + id);
        Shrink(b)?.SetFixedWidth(64f);
        b.End();
    }

    static void AddTierRows(CustomUIBuilder b, int tier,
        (string slot, string label, float min, float max, bool whole)[] table)
    {
        foreach (var p in table)
        {
            b.BeginRow(ROW_SPACING, TextAnchor.MiddleLeft);
            var row = b.CurrentContainer;          // 行容器：稍后整行显隐
            b.AddLabel(p.label);
            Shrink(b);
            b.AddSlider(p.min, p.max, p.min, value => OnParam(p.slot, value), p.whole, "t_" + p.slot);
            var element = Shrink(b);
            element?.SetInteractable(false);
            b.AddLabel("—", "v_" + p.slot);
            Shrink(b)?.SetFixedWidth(64f);
            b.End();
            if (row != null) tierRows[tier].Add(row);
        }
    }

    static void AddWaveRow(CustomUIBuilder b)
    {
        b.BeginRow(ROW_SPACING, TextAnchor.MiddleLeft);
        var row = b.CurrentContainer;
        b.AddLabel("波形");
        Shrink(b);
        b.AddDropdown(new List<string>(WaveNames), 0, which => OnParam("WaveType", which), "t_Wave");
        var element = Shrink(b);
        element?.SetInteractable(false);
        b.End();
        if (row != null) tierRows[1].Add(row);
    }


    static CustomUIElement Shrink(CustomUIBuilder b)
    {
        var element = b.Last;
        var text = element?.text;
        if (text != null && text.fontSize > 0.01f)
        {
            if (text.enableAutoSizing) text.enableAutoSizing = false;
            text.fontSize *= FONT_SCALE;
        }
        return element;
    }

    static void Section(CustomUIBuilder b, string title)
    {
        b.AddHeader(title);
        Shrink(b);
        b.AddSeparator(null, SEPARATOR_PADDING);
        b.AddSpace(SECTION_GAP * 0.66f);
    }

    // ---------------------------------------------------------------- 三级切换
    static void SetTier(int tier)
    {
        activeTier = Mathf.Clamp(tier, 0, Tiers.Length - 1);
        if (window != null && window.IsAlive)
        {
            for (var i = 0; i < Tiers.Length; i++)
            {
                var button = window.Get("tier" + i);
                if (button == null) continue;
                button.SetText((i == activeTier ? "[当前] " : "") + Tiers[i]);
                button.SetInteractable(i != activeTier);
            }
            // 整行显隐：只藏滑条会留下孤零零的标签
            for (var i = 0; i < tierRows.Length; i++)
                foreach (var row in tierRows[i])
                    if (row != null) row.gameObject.SetActive(i == activeTier);
        }
        RefreshParams();
    }

    // ---------------------------------------------------------------- 选择
    static void StepChar(int delta)
    {
        if (cast.Count == 0) return;
        charIndex = (charIndex + delta + cast.Count) % cast.Count;
        layerIndex = 0;
        SelectChar(charIndex);
    }

    static void StepLayer(int delta)
    {
        var count = string.IsNullOrEmpty(selected) ? 0 : VoiceBank.LayerCount(selected);
        if (count <= 0) return;
        layerIndex = (layerIndex + delta + count) % count;
        RefreshLayerName();
        RefreshParams();
        PublishFocus();
        Audition(selected);
    }

    static void AddLayer()
    {
        if (string.IsNullOrEmpty(selected)) return;
        if (!VoiceBank.AddLayer(selected)) return;
        layerIndex = VoiceBank.LayerCount(selected) - 1;   // 跳到新加的那层
        MarkDirty();
        RefreshLayerName();
        RefreshParams();
        Audition(selected);
    }

    static void RemoveLayer()
    {
        if (string.IsNullOrEmpty(selected)) return;
        if (!VoiceBank.RemoveLayer(selected, layerIndex)) return;
        layerIndex = Mathf.Clamp(layerIndex, 0, Mathf.Max(0, VoiceBank.LayerCount(selected) - 1));
        MarkDirty();
        RefreshLayerName();
        RefreshParams();
        Audition(selected);
    }

    static void MarkDirty()
    {
        dirty = true;
        dirtyAt = Time.unscaledTime;
    }

    static void SelectChar(int which, bool preview = true)
    {
        if (which < 0 || which >= cast.Count) return;
        charIndex = which;
        selected = cast[which].preset;
        layerIndex = Mathf.Clamp(layerIndex, 0, Mathf.Max(0, VoiceBank.LayerCount(selected) - 1));
        if (window == null || !window.IsAlive) return;

        var mark = VoiceBank.HasOverride(selected) ? "  (已改)" : "";
        var title = cast[which].zh == selected
            ? $"{cast[which].zh}{mark}"
            : $"{cast[which].zh}{mark}   〔{selected}〕";
        window.Get("curname")?.SetText(title);

        RefreshLayerName();
        RefreshParams();
        PublishFocus();
        if (preview) Audition(selected);
    }

    static void PublishFocus()
    {
        VoiceAgent.FocusPreset = selected ?? "";
        VoiceAgent.FocusLayer = layerIndex;
        VoiceAgent.FocusTier = activeTier;
        VoiceAgent.Publish();
    }

    static void RefreshLayerName()
    {
        if (window == null || !window.IsAlive) return;
        var count = string.IsNullOrEmpty(selected) ? 0 : VoiceBank.LayerCount(selected);
        if (count == 0)
        {
            window.Get("layername")?.SetText("—");
            return;
        }
        var wave = VoiceBank.WaveOf(selected, layerIndex);
        var waveName = wave >= 0 && wave < WaveNames.Length ? WaveNames[wave] : wave.ToString();
        window.Get("layername")?.SetText($"第 {layerIndex + 1} / {count} 层 · {waveName}");
    }

    static void RefreshParams()
    {
        if (window == null || !window.IsAlive || string.IsNullOrEmpty(selected)) return;
        suppress = true;
        try
        {
            Fill(BasicParams);
            Fill(IntermediateParams);
            Fill(AdvancedParams);
            var wave = window.Get("t_Wave");
            if (wave != null)
            {
                wave.SetInteractable(true);
                wave.SetIndex(Mathf.Clamp(VoiceBank.WaveOf(selected, layerIndex), 0, WaveNames.Length - 1));
            }
        }
        finally { suppress = false; }
    }

    static void Fill((string slot, string label, float min, float max, bool whole)[] table)
    {
        foreach (var p in table)
        {
            var element = window.Get("t_" + p.slot);
            if (element == null) continue;
            if (VoiceBank.TryGet(selected, layerIndex, p.slot, out var value))
            {
                element.SetInteractable(true);
                element.SetFloat(Mathf.Clamp(value, p.min, p.max));
                ShowValue(p.slot, Mathf.Clamp(value, p.min, p.max), p.whole);
            }
            else
            {
                element.SetInteractable(false);
                window.Get("v_" + p.slot)?.SetText("—");
            }
        }
    }

    /// <summary>滑条旁边的数值显示：整数参数不带小数，其余最多三位。</summary>
    static string Fmt(float value, bool whole)
    {
        return whole ? Mathf.RoundToInt(value).ToString() : value.ToString("0.###");
    }

    static void ShowValue(string slot, float value, bool whole)
    {
        window?.Get("v_" + slot)?.SetText(Fmt(value, whole));
    }

    static void OnParam(string slot, float value)
    {
        if (suppress || string.IsNullOrEmpty(selected)) return;
        if (!VoiceBank.Set(selected, layerIndex, slot, value)) return;
        var whole = slot == "hz" || slot == "delay";
        ShowValue(slot, value, whole);
        VoiceAgent.FocusPreset = selected;
        VoiceAgent.FocusLayer = layerIndex;
        VoiceAgent.FocusTier = activeTier;
        dirty = true;
        dirtyAt = Time.unscaledTime;
        RefreshLayerName();

        if (Time.unscaledTime - lastAudition < 0.12f) return;
        lastAudition = Time.unscaledTime;
        Audition(selected);
    }

    // ---------------------------------------------------------------- 包
    static List<string> PackLabels()
    {
        var labels = new List<string>();
        foreach (var pack in VoiceBank.Packs) labels.Add(VoiceBank.DisplayName(pack));
        return labels;
    }

    static void SwitchPack(int which)
    {
        if (suppress) return;
        var packs = new List<string>(VoiceBank.Packs);
        if (which < 0 || which >= packs.Count) return;
        if (!VoiceBank.Apply(packs[which])) return;
        window?.Get("status")?.SetText($"生效：{VoiceBank.ActiveDisplayName} · 预设 {VoiceBank.PresetCount} 个");
        packName = VoiceBank.ActiveDisplayName + " 自定义";
        SaveIfNeeded();
        RefreshBank();
    }

    static void Rescan()
    {
        SaveIfNeeded();
        PersonaResolver.Load(null);
        VoiceBank.Rescan();
        RefreshBank();
        Debug.Log($"{Tag} 重新扫描：{VoiceBank.Packs.Count} 个包");
    }

    static void Export()
    {
        SaveIfNeeded();
        var file = SafeName(packName);
        if (file.Length == 0) file = "custom";
        var path = VoiceBank.Export(file, packName);
        if (path == null) return;
        Rescan();
        Debug.Log($"{Tag} 已导出到 {path}");
    }

    static string SafeName(string raw)
    {
        if (string.IsNullOrEmpty(raw)) return "";
        var sb = new StringBuilder();
        foreach (var c in raw.Trim())
        {
            if (char.IsLetterOrDigit(c) || c == '_' || c == '-') sb.Append(c);
            else if (c == ' ' || c == '　') sb.Append('-');
        }
        return sb.ToString().Trim('-');
    }

    static void ShowPacksFolder()
    {
        var folder = Path.Combine(PersonaResolver.Folder ?? "", "packs");
        Debug.Log($"{Tag} 音色包文件夹：{folder}");
        try { System.Diagnostics.Process.Start("explorer.exe", folder.Replace('/', '\\')); }
        catch (Exception e) { Debug.LogWarning($"{Tag} 打开文件夹失败：{e.Message}"); }
    }

    static void RebuildCast()
    {
        cast = PersonaResolver.All();
        cast.RemoveAll(item => !VoiceBank.Contains(item.preset));
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var item in cast) seen.Add(item.preset);
        foreach (var name in VoiceBank.PresetNames)
            if (seen.Add(name)) cast.Add((name, name, "预设"));
        var index = cast.FindIndex(item => item.preset == selected);
        charIndex = index >= 0 ? index : Mathf.Clamp(charIndex, 0, Mathf.Max(0, cast.Count - 1));
    }

    public static void RefreshBank()
    {
        RebuildCast();
        if (window == null || !window.IsAlive) return;
        suppress = true;
        try
        {
            var labels = PackLabels();
            window.Get("packsel")?.SetOptions(labels);
            window.Get("packsel")?.SetIndex(Mathf.Max(0, labels.IndexOf(VoiceBank.ActiveDisplayName)));
        }
        finally { suppress = false; }
        window.Get("status")?.SetText($"生效：{VoiceBank.ActiveDisplayName} · 预设 {VoiceBank.PresetCount} 个");
        if (cast.Count > 0) SelectChar(charIndex, false);
        else { selected = null; window.Get("curname")?.SetText("无可用预设"); }
    }

    public static void ReapplyAudio()
    {
        if (audition != null && DialogueBlipsMod.Current != null) audition.volume = DialogueBlipsMod.Current.CurrentVolume();
    }

    public static void Shutdown()
    {
        SaveIfNeeded();
        if (window != null && window.IsAlive) window.Close();
        window = null;
        if (audition != null) { audition.Stop(); UnityEngine.Object.Destroy(audition.gameObject); }
        audition = null;
        foreach (var rows in tierRows) rows.Clear();
        cast.Clear(); selected = null;
    }

    /// <summary>给 Agent 接口用的试听入口。</summary>
    public static void PlayPreview(string preset) => Audition(preset);

    static void Audition(string preset)
    {
        if (audition == null)
        {
            var go = new GameObject("DialogueBlipsAudition");
            UnityEngine.Object.DontDestroyOnLoad(go);
            audition = go.AddComponent<AudioSource>();
            audition.playOnAwake = false;
            audition.spatialBlend = 0f;
            audition.volume = 0f;
        }
        var pool = VoiceBank.Pool(preset);
        if (pool == null || pool.Length == 0) return;
        ReapplyAudio();
        audition.Stop();
        audition.PlayOneShot(pool[UnityEngine.Random.Range(0, pool.Length)]);
    }
}

/// <summary>热键驱动。IMod 没有 Update，借一个常驻 MonoBehaviour。</summary>
internal sealed class PanelHotkey : MonoBehaviour
{
    void Update()
    {
        if (Input.GetKeyDown(KeyCode.F11)) Panel.Toggle();
        Panel.Tick();
        if (Panel.IsOpen) VoiceAgent.Poll();
    }

    void OnDisable() => Panel.SaveIfNeeded();
}
