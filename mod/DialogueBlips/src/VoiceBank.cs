using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;
using Wikman.Synthesizer.Sfxr;

/// <summary>
/// 声音库：读预设包，按需合成 AudioClip 池，供逐字播放。
///
/// 两个关键决定：
/// 1) **预渲染而不是每字实时合成**——每个预设先渲 8 个基频抖动 ±6% 的变体，
///    打字时随机取一个。这样每字只剩一次 PlayOneShot，没有合成开销。
/// 2) **按需渲染而不是启动全渲**——第一次用到某个角色时才渲他那 8 个，
///    避免开局卡一下（18 个预设 × 8 变体 × 1~4 层）。
/// </summary>
internal static class VoiceBank
{
    const int SampleRate = 44100;
    const int VariantsPerPreset = 8;
    const float PitchJitter = 0.06f;

    /// <summary>预设名 -> 层定义（来自预设包）。</summary>
    static readonly Dictionary<string, List<Layer>> presets = new Dictionary<string, List<Layer>>(StringComparer.Ordinal);
    /// <summary>预设名 -> 渲染好的 clip 池（惰性填充）。</summary>
    static readonly Dictionary<string, AudioClip[]> pools = new Dictionary<string, AudioClip[]>(StringComparer.Ordinal);
    static readonly List<string> loadedPacks = new List<string>();

    /// <summary>层：一组 31 项 bfxr 参数 + 音高/增益/延迟。</summary>
    internal sealed class Layer
    {
        public float hz = 200f;
        public float gain = 1f;
        public float delay;
        public bool mute;
        public Dictionary<ParameterType, float> p;
    }

    public static bool Ready => presets.Count > 0;
    public static int PresetCount => presets.Count;
    public static IList<string> Packs => loadedPacks;

    public static List<string> PresetNames
    {
        get
        {
            var list = new List<string>(presets.Keys);
            list.Sort(StringComparer.Ordinal);
            return list;
        }
    }

    /// <summary>预设主层的基频，给面板显示用。</summary>
    public static float PitchOf(string preset)
    {
        return presets.TryGetValue(preset, out var layers) && layers.Count > 0 ? layers[0].hz : 0f;
    }

    // ---------------------------------------------------------------- 载入
    /// <summary>每个包文件解析出来的预设（缓存住，切换时不用重新读盘）。</summary>
    static readonly Dictionary<string, Dictionary<string, List<Layer>>> packCache =
        new Dictionary<string, Dictionary<string, List<Layer>>>(StringComparer.OrdinalIgnoreCase);
    /// <summary>每个包文件的原始 JSON（导出时以它为模板，保留 characters / mapping）。</summary>
    static readonly Dictionary<string, JObject> packDocs = new Dictionary<string, JObject>(StringComparer.OrdinalIgnoreCase);

    public static string ActivePack { get; private set; } = "";

    /// <summary>包的显示名：用包里的 name 字段（可以是中文），没有就退回文件名。</summary>
    public static string DisplayName(string packFile)
    {
        if (string.IsNullOrEmpty(packFile)) return "";
        if (packDocs.TryGetValue(packFile, out var doc))
        {
            var name = (string)doc["name"];
            if (!string.IsNullOrEmpty(name)) return name;
        }
        return packFile;
    }

    public static string ActiveDisplayName => DisplayName(ActivePack);
    static string modRoot = "";

    public static void Load(string modFolder)
    {
        var nextRoot = modFolder ?? "";
        var sameRoot = string.Equals(modRoot, nextRoot, StringComparison.OrdinalIgnoreCase);
        var previousCache = sameRoot
            ? new Dictionary<string, Dictionary<string, List<Layer>>>(packCache, StringComparer.OrdinalIgnoreCase)
            : new Dictionary<string, Dictionary<string, List<Layer>>>();
        var previousDocs = sameRoot ? new Dictionary<string, JObject>(packDocs) : new Dictionary<string, JObject>();
        // Never tear down a working library because a rescan cannot read its directory.
        var packDir = Path.Combine(nextRoot, "packs");
        // 音色包可以放在别的 Mod 里（娘化包就是独立的纯数据 Mod）。
        // 先扫自己的 packs/，再把 Mods/ 下所有兄弟 Mod 的 packs/ 也扫进来。
        var files = new List<string>();
        try { files.AddRange(System.IO.Directory.GetFiles(packDir, "*.json")); }
        catch (Exception e)
        {
            Debug.LogWarning("[DialogueBlips] 扫描失败，保留当前声音库：" + e.Message);
            return;
        }
        try
        {
            var modsRoot = Path.GetDirectoryName(nextRoot.TrimEnd('\\', '/'));
            if (!string.IsNullOrEmpty(modsRoot) && System.IO.Directory.Exists(modsRoot))
                foreach (var other in System.IO.Directory.GetDirectories(modsRoot, "packs", SearchOption.AllDirectories))
                    if (!string.Equals(other, packDir, StringComparison.OrdinalIgnoreCase))
                        files.AddRange(System.IO.Directory.GetFiles(other, "*.json"));
        }
        catch (Exception e)
        {
            Debug.LogWarning("[DialogueBlips] 扫描兄弟 Mod 的 packs 失败（只用自己目录）：" + e.Message);
        }
        files.Sort((a, b) => string.Compare(a, b, StringComparison.OrdinalIgnoreCase));
        if (!string.Equals(modRoot, nextRoot, StringComparison.OrdinalIgnoreCase))
        {
            packOverrides.Clear(); packStructures.Clear(); overridesLoaded = false;
            savedActivePack = "";
        }
        presets.Clear();
        ReleasePools();
        ActivePack = "";
        loadedPacks.Clear();
        packCache.Clear();
        packDocs.Clear();
        modRoot = modFolder ?? "";
        if (string.IsNullOrEmpty(modFolder)) return;

        files.Sort((a, b) => string.Compare(a, b, StringComparison.OrdinalIgnoreCase));
        foreach (var file in files)
        {
            try
            {
                var layers = ParsePack(file, out var doc);
                if (layers == null) continue;
                var name = Path.GetFileNameWithoutExtension(file);
                packCache[name] = layers;
                packDocs[name] = doc;
                loadedPacks.Add(name);
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[DialogueBlips] 预设包 {Path.GetFileName(file)} 载入失败：{e.Message}");
                var name = Path.GetFileNameWithoutExtension(file);
                if (previousCache.TryGetValue(name, out var previous))
                {
                    packCache[name] = previous;
                    packDocs[name] = previousDocs[name];
                    loadedPacks.Add(name);
                    Debug.LogWarning("[DialogueBlips] 保留此包的上一次有效版本：" + name);
                }
            }
        }

        // 默认包的选择顺序：
        //   1. 声明了 requiresMod 且那个模组已启用的包（娘化包 + 娘化立绘）
        //   2. target=vanilla 的包
        //   3. 文件名排序的第一个
        // 这样娘化包只有在配套立绘模组一起启用时才会自动接管。
        string preferred = null;
        string reason = "文件名排序";
        foreach (var name in loadedPacks)
        {
            if (!packDocs.TryGetValue(name, out var doc)) continue;
            var required = (string)doc["requiresMod"];
            if (string.IsNullOrEmpty(required)) continue;
            var active = RequiresSatisfied(required);
            if (!active) continue;
            preferred = name;
            reason = "娘化立绘模组已启用";
            Debug.Log($"[DialogueBlips] 检测到娘化立绘已启用（工坊 {PortraitWorkshopId}），优先使用 {name}");
            break;
        }
        if (preferred == null)
            foreach (var name in loadedPacks)
                if (packDocs.TryGetValue(name, out var doc) && (string)doc["target"] == "vanilla")
                { preferred = name; reason = "target=vanilla"; break; }
        if (preferred == null && loadedPacks.Count > 0) preferred = loadedPacks[0];
        if (!overridesLoaded) ReadOverrides();
        if (!string.IsNullOrEmpty(savedActivePack) && packCache.ContainsKey(savedActivePack))
        { preferred = savedActivePack; reason = "玩家上次选择"; }
        if (preferred != null)
        {
            Debug.Log($"[DialogueBlips] 默认音色包按「{reason}」选定：{preferred}");
            if (!Apply(preferred)) Apply(DefaultPack());
        }
        Debug.Log($"[DialogueBlips] 声音库就绪：{presets.Count} 个预设（来自 {loadedPacks.Count} 个包）");
    }

    /// <summary>娘化立绘模组的工坊 ID（用户 2026-10-30 提供）。</summary>
    const ulong PortraitWorkshopId = 3828971372UL;

    /// <summary>某个模组是不是启用着。匹配方式：Mod ID 或创意工坊 ID 都算。</summary>
    static bool IsModEnabled(string token)
    {
        if (string.IsNullOrEmpty(token)) return false;
        try
        {
            foreach (var mod in ModLoader.Mods)
            {
                if (mod == null || !mod.IsEnabled) continue;
                if (mod.Manifest != null && mod.Manifest.ID == token) return true;
                if (mod.WorkshopId != 0 && mod.WorkshopId.ToString() == token) return true;
            }
        }
        catch (Exception e)
        {
            Debug.LogWarning($"[DialogueBlips] 查模组 {token} 失败：{e.Message}");
        }
        return false;
    }

    /// <summary>娘化立绘模组是否启用。工坊 ID 和 Mod ID 任一命中都算——
    /// 工坊订阅的 WorkshopId 是 3828971372，本地装的 Mod ID 是 player.launchgiftportraits。</summary>
    static bool PortraitModEnabled()
    {
        return IsModEnabled(PortraitWorkshopId.ToString())
            || IsModEnabled("player.launchgiftportraits");
    }

    /// <summary>包声明的依赖满不满足。写成 "portrait" 或工坊 ID 都指娘化立绘。</summary>
    static bool RequiresSatisfied(string required)
    {
        if (string.IsNullOrEmpty(required)) return false;
        if (required == "portrait" || required == PortraitWorkshopId.ToString())
            return PortraitModEnabled();
        return IsModEnabled(required);
    }

    /// <summary>切换生效的音色包。玩家改动会在新包之上重新应用。</summary>
    public static bool Apply(string name)
    {
        if (string.IsNullOrEmpty(name) || !packCache.ContainsKey(name))
        {
            Debug.LogWarning($"[DialogueBlips] 切包失败，没有这个包：{name}");
            return false;
        }
        var layers = BaseDefinitions(name);
        if (layers.Count > 64)
        {
            Debug.LogWarning("[DialogueBlips] 切包失败：合并默认音色后超过 64 个预设");
            return false;
        }
        presets.Clear();
        foreach (var pair in layers) presets[pair.Key] = CloneLayers(pair.Value);
        ReleasePools();
        ActivePack = name;
        ApplySavedOverrides();
        Debug.Log($"[DialogueBlips] 生效音色包：{name}（{presets.Count} 个预设）");
        return true;
    }

    /// <summary>解析一个包文件。返回 null 表示格式不认识。</summary>
    static Dictionary<string, List<Layer>> ParsePack(string path, out JObject doc)
    {
        doc = JObject.Parse(File.ReadAllText(path));
        VoiceValidation.Pack(doc);
        var format = (string)doc["format"];
        if (format != "dsp-voicepack/1")
        {
            Debug.LogWarning($"[DialogueBlips] {Path.GetFileName(path)} 格式不支持：{format}");
            return null;
        }

        var target = (string)doc["target"] ?? "vanilla";
        var packPresets = doc["presets"] as JObject;
        if (packPresets == null) return null;

        var result = new Dictionary<string, List<Layer>>(StringComparer.Ordinal);
        foreach (var kv in packPresets)
        {
            var layers = new List<Layer>();
            foreach (var node in kv.Value.Children<JObject>())
            {
                var layer = new Layer
                {
                    hz = (float?)node["hz"] ?? 200f,
                    gain = (float?)node["gain"] ?? 1f,
                    delay = (float?)node["delay"] ?? 0f,
                    mute = (bool?)node["mute"] ?? false,
                    p = new Dictionary<ParameterType, float>(),
                };
                var p = node["p"] as JObject;
                if (p != null)
                {
                    foreach (var param in p)
                    {
                        if (Enum.TryParse<ParameterType>(param.Key, true, out var type) && type != ParameterType.None)
                            layer.p[type] = (float)param.Value;
                    }
                }
                layers.Add(layer);
            }
            if (layers.Count > 0) result[kv.Key] = layers;
        }
        Debug.Log($"[DialogueBlips]   {Path.GetFileName(path)} → {result.Count} 个预设（target={target}）");
        return result;
    }

    /// <summary>把当前预设（含玩家改动）导出成一个新的音色包文件。</summary>
    public static string Export(string id, string displayName)
    {
        if (string.IsNullOrEmpty(modRoot)) return null;
        if (!packDocs.TryGetValue(ActivePack, out var template))
        {
            Debug.LogWarning("[DialogueBlips] 导出失败：没有可用的模板包");
            return null;
        }

        var doc = (JObject)template.DeepClone();
        var presetsNode = new JObject();
        foreach (var pair in presets)
        {
            var array = new JArray();
            foreach (var layer in pair.Value)
            {
                var p = new JObject();
                foreach (var param in layer.p) p[param.Key.ToString()] = param.Value;
                array.Add(new JObject
                {
                    ["hz"] = layer.hz,
                    ["gain"] = layer.gain,
                    ["delay"] = layer.delay,
                    ["mute"] = layer.mute,
                    ["p"] = p,
                });
            }
            presetsNode[pair.Key] = array;
        }
        doc["presets"] = presetsNode;
        doc["id"] = id;
        doc["name"] = string.IsNullOrEmpty(displayName) ? id : displayName;
        doc["version"] = "1.0.0";

        if (string.IsNullOrWhiteSpace(id) || Path.GetFileName(id) != id || id.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
            throw new ArgumentException("非法包文件名");
        var path = Path.Combine(modRoot, "packs", id + ".json");
        VoiceValidation.Pack(doc);
        AtomicFile.Write(path, doc.ToString());
        Debug.Log($"[DialogueBlips] 已导出音色包：{path}（{presets.Count} 个预设）");
        return path;
    }

    /// <summary>重新扫一遍 packs 目录（玩家丢进新文件后不用重启游戏）。</summary>
    public static void Rescan()
    {
        var active = ActivePack;
        SaveOverrides(modRoot);
        Load(modRoot);
        if (!string.IsNullOrEmpty(active) && packCache.ContainsKey(active)) Apply(active);
    }

    // ---------------------------------------------------------------- 渲染
    /// <summary>取某个预设的 clip 池；第一次调用时才合成。</summary>
    public static AudioClip[] Pool(string preset)
    {
        if (string.IsNullOrEmpty(preset)) return null;
        if (pools.TryGetValue(preset, out var cached)) return cached;
        if (!presets.TryGetValue(preset, out var layers)) return null;

        var clips = new AudioClip[VariantsPerPreset];
        var random = new System.Random(preset.GetHashCode());
        for (var i = 0; i < VariantsPerPreset; i++)
        {
            var jitter = 1f + (float)(random.NextDouble() * 2 - 1) * PitchJitter;
            clips[i] = Render(preset, layers, jitter, i);
        }
        pools[preset] = clips;
        return clips;
    }

    public static bool Contains(string preset) => preset != null && presets.ContainsKey(preset);

    public static string MappedPreset(string key, string fallback)
    {
        if (packDocs.TryGetValue(ActivePack, out var doc) && doc["mapping"] is JObject map
            && map[key]?.Type == JTokenType.String) return (string)map[key];
        return fallback;
    }

    static void InvalidatePool(string preset)
    {
        if (!pools.TryGetValue(preset, out var clips)) return;
        // Existing one-shots may still be playing. Retire after their maximum lifetime.
        foreach (var clip in clips)
            if (clip != null) UnityEngine.Object.Destroy(clip, clip.length + 0.1f);
        pools.Remove(preset);
    }

    public static void ReleasePools()
    {
        foreach (var key in new List<string>(pools.Keys)) InvalidatePool(key);
    }

    static List<Layer> CloneLayers(List<Layer> layers)
    {
        var result = new List<Layer>();
        foreach (var layer in layers) result.Add(CloneLayer(layer));
        return result;
    }

    static void RememberStructure(string preset, List<Layer> layers)
    {
        structureOverrides[preset] = CloneLayers(layers);
        foreach (var key in new List<string>(overrides.Keys))
            if (key.StartsWith(preset + "|", StringComparison.Ordinal)) overrides.Remove(key);
    }

    static AudioClip Render(string name, List<Layer> layers, float jitter, int index)
    {
        var samples = Mix(layers, jitter);
        var clip = AudioClip.Create($"{name}#{index}", samples.Length, 1, SampleRate, false);
        clip.SetData(samples, 0);
        return clip;
    }

    static float[] Mix(List<Layer> layers, float jitter)
    {
        var rendered = new List<(float[] data, int at, float gain)>();
        var length = 0;
        foreach (var layer in layers)
        {
            if (layer.mute || layer.gain == 0f || layer.p == null || layer.p.Count == 0) continue;

            // 音高只存在层的 hz 上（预设包的 p 里没有 StartFrequency），
            // 这里乘抖动再换算成 bfxr 的 StartFrequency：f = 3528 × (s² + 0.001)
            var params_ = new Dictionary<ParameterType, float>(layer.p);
            var hz = Mathf.Clamp(layer.hz * jitter, 20f, 3500f);
            params_[ParameterType.StartFrequency] =
                Mathf.Sqrt(Mathf.Max(hz / 3528f - 0.001f, 0f));

            var synth = new SfxrInterface();
            synth.CreateWithData(params_, out var buffer, out var count, out _);

            var at = Mathf.Max(0, (int)(layer.delay / 1000f * SampleRate));
            rendered.Add((buffer, at, layer.gain));
            length = Mathf.Max(length, at + count);
        }
        if (length <= 0) return new float[1];

        var mix = new float[length];
        foreach (var (data, at, gain) in rendered)
            for (var i = 0; i < data.Length && at + i < length; i++)
                mix[at + i] += data[i] * gain;

        var peak = 0f;
        foreach (var value in mix) peak = Mathf.Max(peak, Mathf.Abs(value));
        if (peak > 0.95f)
        {
            var scale = 0.95f / peak;
            for (var i = 0; i < mix.Length; i++) mix[i] *= scale;
        }
        return mix;
    }

    // ---------------------------------------------------------------- 编辑与覆盖
    /// <summary>玩家改过的标量。**按包分组**——改动跟着包走，切包不会互相盖。
    /// 结构：包文件名 → ("预设|层|参数" → 值)。</summary>
    static readonly Dictionary<string, Dictionary<string, float>> packOverrides =
        new Dictionary<string, Dictionary<string, float>>(StringComparer.OrdinalIgnoreCase);

    /// <summary>当前生效包的那一份（省得到处写两层索引）。</summary>
    static Dictionary<string, float> overrides
    {
        get
        {
            if (!packOverrides.TryGetValue(ActivePack ?? "", out var table))
            {
                table = new Dictionary<string, float>(StringComparer.Ordinal);
                packOverrides[ActivePack ?? ""] = table;
            }
            return table;
        }
    }

    public static bool HasOverride(string preset)
    {
        if (structureOverrides.ContainsKey(preset)) return true;
        foreach (var key in overrides.Keys)
            if (key.StartsWith(preset + "|", StringComparison.Ordinal)) return true;
        return false;
    }

    public static bool HasOverride(string preset, int layerIndex)
    {
        if (structureOverrides.ContainsKey(preset)) return true;
        var prefix = preset + "|" + layerIndex + "|";
        foreach (var key in overrides.Keys)
            if (key.StartsWith(prefix, StringComparison.Ordinal)) return true;
        return false;
    }

    /// <summary>玩家改过层结构的预设，同样按包分组：包文件名 → (预设 → 整份层表)。</summary>
    static readonly Dictionary<string, Dictionary<string, List<Layer>>> packStructures =
        new Dictionary<string, Dictionary<string, List<Layer>>>(StringComparer.OrdinalIgnoreCase);

    static Dictionary<string, List<Layer>> structureOverrides
    {
        get
        {
            if (!packStructures.TryGetValue(ActivePack ?? "", out var table))
            {
                table = new Dictionary<string, List<Layer>>(StringComparer.Ordinal);
                packStructures[ActivePack ?? ""] = table;
            }
            return table;
        }
    }

    /// <summary>复制一个层，用来加层。</summary>
    static Layer CloneLayer(Layer source)
    {
        return new Layer
        {
            hz = source.hz,
            gain = source.gain,
            delay = source.delay,
            mute = source.mute,
            p = source.p == null
                ? new Dictionary<ParameterType, float>()
                : new Dictionary<ParameterType, float>(source.p),
        };
    }

    /// <summary>加一层：复制最后一层并降一半音量，避免一上来就翻倍变响。</summary>
    public static bool AddLayer(string preset)
    {
        if (!presets.TryGetValue(preset, out var layers) || layers.Count == 0) return false;
        if (layers.Count >= 8) return false;          // 跟服务端校验上限一致
        var copy = CloneLayer(layers[layers.Count - 1]);
        copy.gain *= 0.5f;
        layers.Add(copy);
        RememberStructure(preset, layers);
        InvalidatePool(preset);
        return true;
    }

    /// <summary>删一层。至少保留一层。</summary>
    public static bool RemoveLayer(string preset, int layerIndex)
    {
        if (!presets.TryGetValue(preset, out var layers)) return false;
        if (layers.Count <= 1 || layerIndex < 0 || layerIndex >= layers.Count) return false;
        layers.RemoveAt(layerIndex);
        RememberStructure(preset, layers);
        InvalidatePool(preset);
        return true;
    }

    static JObject LayerToJson(Layer layer)
    {
        var p = new JObject();
        foreach (var param in layer.p) p[param.Key.ToString()] = param.Value;
        return new JObject
        {
            ["hz"] = layer.hz,
            ["gain"] = layer.gain,
            ["delay"] = layer.delay,
            ["mute"] = layer.mute,
            ["p"] = p,
        };
    }

    static Layer LayerFromJson(JObject node)
    {
        VoiceValidation.Layer(node, "override layer");
        var layer = new Layer
        {
            hz = (float?)node["hz"] ?? 200f,
            gain = (float?)node["gain"] ?? 1f,
            delay = (float?)node["delay"] ?? 0f,
            mute = (bool?)node["mute"] ?? false,
            p = new Dictionary<ParameterType, float>(),
        };
        if (node["p"] is JObject p)
            foreach (var param in p)
                if (Enum.TryParse<ParameterType>(param.Key, true, out var type) && type != ParameterType.None)
                    layer.p[type] = (float)param.Value;
        return layer;
    }

    /// <summary>把某一层的全部参数导出成"名字 → 值"，供 Agent 接口暴露当前编辑目标。</summary>
    public static Dictionary<string, float> LayerParams(string preset, int layerIndex)
    {
        var result = new Dictionary<string, float>(StringComparer.Ordinal);
        if (!presets.TryGetValue(preset, out var layers)
            || layerIndex < 0 || layerIndex >= layers.Count) return result;
        var layer = layers[layerIndex];
        result["hz"] = layer.hz;
        result["gain"] = layer.gain;
        result["delay"] = layer.delay;
        foreach (var pair in layer.p) result[pair.Key.ToString()] = pair.Value;
        return result;
    }

    /// <summary>
    /// 预设名解析。娘化包里的预设名带「（娘化）」后缀，而人物键映射用的是原角色名，
    /// 所以查不到时再试一次带后缀的——这样映射表不用为每个包改一份。
    /// </summary>
    public static string ResolveName(string want)
    {
        if (string.IsNullOrEmpty(want)) return want;
        if (presets.ContainsKey(want)) return want;
        var suffixed = want + NyankoSuffix;
        return presets.ContainsKey(suffixed) ? suffixed : want;
    }

    public const string NyankoSuffix = "（娘化）";

    /// <summary>某个预设有几层。面板的层选择用。</summary>
    public static int LayerCount(string preset)
    {
        return presets.TryGetValue(ResolveName(preset), out var layers) ? layers.Count : 0;
    }

    /// <summary>某层的波形编号与名字，面板显示用。</summary>
    public static int WaveOf(string preset, int layerIndex)
    {
        preset = ResolveName(preset);
        if (!presets.TryGetValue(preset, out var layers) || layerIndex < 0 || layerIndex >= layers.Count)
            return 0;
        return layers[layerIndex].p != null
               && layers[layerIndex].p.TryGetValue(ParameterType.WaveType, out var wave)
            ? Mathf.RoundToInt(wave) : 0;
    }

    /// <summary>读某层的某个参数。slot 见下：hz / gain / delay / 或任意 31 项参数名。</summary>
    public static bool TryGet(string preset, int layerIndex, string slot, out float value)
    {
        value = 0f;
        preset = ResolveName(preset);
        if (!presets.TryGetValue(preset, out var layers)
            || layerIndex < 0 || layerIndex >= layers.Count) return false;
        var layer = layers[layerIndex];
        switch (slot)
        {
            case "hz": value = layer.hz; return true;
            case "gain": value = layer.gain; return true;
            case "delay": value = layer.delay; return true;
            default:
                return Enum.TryParse<ParameterType>(slot, true, out var type)
                       && layer.p.TryGetValue(type, out value);
        }
    }

    /// <summary>改某层的一个参数：改内存、记进 overrides、丢掉旧的 clip 池。</summary>
    public static bool Set(string preset, int layerIndex, string slot, float value)
    {
        preset = ResolveName(preset);
        if (!presets.TryGetValue(preset, out var layers)
            || layerIndex < 0 || layerIndex >= layers.Count) return false;
        try { VoiceValidation.Value(slot, value); }
        catch (ArgumentException) { return false; }
        if (TryGet(preset, layerIndex, slot, out var previous) && previous == value) return true;
        var layer = layers[layerIndex];
        switch (slot)
        {
            case "hz": layer.hz = value; break;
            case "gain": layer.gain = value; break;
            case "delay": layer.delay = value; break;
            default:
                if (!Enum.TryParse<ParameterType>(slot, false, out var type)) return false;
                layer.p[type] = value;
                break;
        }
        overrides[preset + "|" + layerIndex + "|" + slot] = value;
        if (structureOverrides.ContainsKey(preset)) RememberStructure(preset, layers);
        InvalidatePool(preset);
        return true;
    }

    /// <summary>当前生效包的改动数（面板显示用）。</summary>
    public static int OverrideCount => overrides.Count + structureOverrides.Count;

    /// <summary>所有包的改动总数（决定要不要写盘）。</summary>
    public static int TotalOverrides
    {
        get
        {
            var total = 0;
            foreach (var table in packOverrides.Values) total += table.Count;
            foreach (var table in packStructures.Values) total += table.Count;
            return total;
        }
    }

    /// <summary>把玩家改动写到 &lt;mod&gt;/overrides.json。加载时它在所有包之后应用。</summary>
    public static bool SaveOverrides(string modFolder)
    {
        if (string.IsNullOrEmpty(modFolder)) return false;
        // Failed initial loading must never replace a user's unread document.
        if (!Ready || !overridesLoaded || !string.Equals(modRoot, modFolder, StringComparison.OrdinalIgnoreCase)) return false;
        try
        {
            var doc = new JObject
            {
                ["format"] = "dsp-overrides/2",
                ["activePack"] = ActivePack,
                ["note"] = "玩家在游戏内面板改的值。按音色包分组——切包不会互相覆盖。",
            };
            var packsNode = new JObject();
            var packNames = new HashSet<string>(packOverrides.Keys, StringComparer.OrdinalIgnoreCase);
            packNames.UnionWith(packStructures.Keys);
            foreach (var pack in packNames)
            {
                if (!packOverrides.TryGetValue(pack, out var values)) values = new Dictionary<string, float>();
                packStructures.TryGetValue(pack, out var structures);
                if (values.Count == 0 && (structures == null || structures.Count == 0)) continue;

                var node = new JObject();
                if (values.Count > 0)
                {
                    var v = new JObject();
                    foreach (var pair in values) v[pair.Key] = pair.Value;
                    node["values"] = v;
                }
                if (structures != null && structures.Count > 0)
                {
                    var ls = new JObject();
                    foreach (var pair in structures)
                    {
                        var array = new JArray();
                        foreach (var layer in pair.Value) array.Add(LayerToJson(layer));
                        ls[pair.Key] = array;
                    }
                    node["layers"] = ls;
                }
                packsNode[pack] = node;
            }
            doc["packs"] = packsNode;
            AtomicFile.Write(Path.Combine(modFolder, "overrides.json"), doc.ToString());
            savedActivePack = ActivePack;
            Debug.Log($"[DialogueBlips] 已保存 {TotalOverrides} 项改动（{packOverrides.Count} 个包）");
            return true;
        }
        catch (Exception e)
        {
            Debug.LogWarning($"[DialogueBlips] 保存改动失败：{e.Message}");
            return false;
        }
    }

    static bool overridesLoaded;
    static string savedActivePack = "";

    /// <summary>读一次 overrides.json 进 overrides 表；之后每次切包都重放。</summary>
    static void ReadOverrides()
    {
        overridesLoaded = true;
        if (string.IsNullOrEmpty(modRoot)) return;
        foreach (var path in new[] { Path.Combine(modRoot, "overrides.json"), Path.Combine(modRoot, "overrides.json.bak") })
        {
            if (!File.Exists(path)) continue;
            try
            {
                var doc = JObject.Parse(File.ReadAllText(path));
                var format = (string)doc["format"];
                if (format != "dsp-overrides/1" && format != "dsp-overrides/2") throw new ArgumentException("不支持的覆盖格式");
                if (doc["packs"] != null && !(doc["packs"] is JObject)) throw new ArgumentException("packs 必须是对象");
                if (doc["activePack"] != null && doc["activePack"].Type != JTokenType.String) throw new ArgumentException("activePack 必须是字符串");
                var selected = (string)doc["activePack"] ?? "";
                var valuesByPack = new Dictionary<string, Dictionary<string, float>>(StringComparer.OrdinalIgnoreCase);
                var layersByPack = new Dictionary<string, Dictionary<string, List<Layer>>>(StringComparer.OrdinalIgnoreCase);
                var nodes = doc["packs"] as JObject;
                if (nodes == null)
                    nodes = new JObject { [ActivePack.Length > 0 ? ActivePack : DefaultPack()] = doc.DeepClone() };
                foreach (var packEntry in nodes)
                {
                    if (!(packEntry.Value is JObject)) throw new ArgumentException("覆盖包必须是对象");
                    foreach (var field in new[] { "values", "layers" })
                        if (packEntry.Value[field] != null && !(packEntry.Value[field] is JObject)) throw new ArgumentException(field + " 必须是对象");
                    var values = new Dictionary<string, float>(StringComparer.Ordinal);
                    var structures = new Dictionary<string, List<Layer>>(StringComparer.Ordinal);
                    if (packEntry.Value["values"] is JObject scalar)
                        foreach (var pair in scalar)
                        {
                            var key = pair.Key;
                            var parts = key.Split('|');
                            if (parts.Length == 2) { key = parts[0] + "|0|" + parts[1]; parts = key.Split('|'); }
                            if (parts.Length != 3 || !int.TryParse(parts[1], out var index) || index < 0 || index >= 8)
                                throw new ArgumentException("非法覆盖键：" + key);
                            var value = VoiceValidation.Number(pair.Value, key);
                            VoiceValidation.Value(parts[2], value);
                            values[key] = value;
                        }
                    if (packEntry.Value["layers"] is JObject layerNodes)
                        foreach (var pair in layerNodes)
                        {
                            VoiceValidation.Layers(pair.Value, pair.Key);
                            var layers = new List<Layer>();
                            foreach (var node in (JArray)pair.Value) layers.Add(LayerFromJson((JObject)node));
                            structures[pair.Key] = layers;
                        }
                    valuesByPack[packEntry.Key] = values;
                    layersByPack[packEntry.Key] = structures;
                }
                foreach (var pair in valuesByPack) packOverrides[pair.Key] = pair.Value;
                foreach (var pair in layersByPack) packStructures[pair.Key] = pair.Value;
                savedActivePack = selected;
                Debug.Log($"[DialogueBlips] 读到 {packOverrides.Count} 个包的玩家改动，来源：{path}");
                return;
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[DialogueBlips] 覆盖文件读取失败 {path}：{e.Message}");
                try { File.Copy(path, path + ".invalid-" + DateTime.UtcNow.ToString("yyyyMMddHHmmssfff")); }
                catch (Exception copyError) { Debug.LogWarning("[DialogueBlips] 无法保留损坏文件：" + copyError.Message); }
            }
        }
    }

    /// <summary>把玩家改动重放到当前生效的包上。切包后必须再调一次。</summary>
    static void ApplySavedOverrides()
    {
        if (!overridesLoaded) ReadOverrides();

        foreach (var pair in structureOverrides)
        {
            if (!presets.ContainsKey(pair.Key)) continue;
            var copy = new List<Layer>();
            foreach (var layer in pair.Value) copy.Add(CloneLayer(layer));
            presets[pair.Key] = copy;
            InvalidatePool(pair.Key);
        }

        foreach (var pair in new Dictionary<string, float>(overrides))
        {
            var parts = pair.Key.Split('|');
            if (parts.Length != 3) continue;
            if (!presets.ContainsKey(parts[0])) continue;
            if (int.TryParse(parts[1], out var index)) Set(parts[0], index, parts[2], pair.Value);
        }
    }

    static string DefaultPack()
    {
        if (packCache.ContainsKey("questinggoose.vanilla")) return "questinggoose.vanilla";
        foreach (var name in loadedPacks)
            if ((string)packDocs[name]["target"] == "vanilla") return name;
        return loadedPacks.Count > 0 ? loadedPacks[0] : "";
    }

    static Dictionary<string, List<Layer>> BaseDefinitions(string name)
    {
        var result = new Dictionary<string, List<Layer>>(StringComparer.Ordinal);
        // A partial replacement inherits the shipped vanilla definitions.
        // Its mapping still only points at voices explicitly declared in that pack.
        var fallback = DefaultPack();
        if (packCache.TryGetValue(fallback, out var defaults))
            foreach (var pair in defaults) result[pair.Key] = pair.Value;
        foreach (var pair in packCache[name]) result[pair.Key] = pair.Value;
        return result;
    }

    public static void ApplyBatch(string pack, Dictionary<string, float> changes, string audition)
    {
        var target = string.IsNullOrEmpty(pack) ? ActivePack : pack;
        if (!packCache.ContainsKey(target))
        {
            target = null;
            foreach (var candidate in loadedPacks)
                if (DisplayName(candidate) == pack)
                {
                    if (target != null) throw new ArgumentException("音色包显示名不唯一，请使用文件名");
                    target = candidate;
                }
        }
        if (target == null || !packCache.ContainsKey(target)) throw new ArgumentException("音色包不存在");
        var definitions = BaseDefinitions(target);
        if (definitions.Count > 64) throw new ArgumentException("合并默认音色后超过 64 个预设");
        packStructures.TryGetValue(target, out var structures);
        foreach (var pair in changes)
        {
            var parts = pair.Key.Split('|');
            if (parts.Length != 3 || !int.TryParse(parts[1], out var index)) throw new ArgumentException("非法参数键：" + pair.Key);
            List<Layer> layers = null;
            if (structures == null || !structures.TryGetValue(parts[0], out layers)) definitions.TryGetValue(parts[0], out layers);
            if (layers == null || index < 0 || index >= layers.Count) throw new ArgumentException("预设或层不存在：" + pair.Key);
            VoiceValidation.Value(parts[2], pair.Value);
        }
        if (!string.IsNullOrEmpty(audition) && !definitions.ContainsKey(audition)) throw new ArgumentException("试听预设不存在：" + audition);
        var oldPack = ActivePack;
        var oldValues = new Dictionary<string, float>();
        if (packOverrides.TryGetValue(target, out var existingValues))
            foreach (var pair in existingValues) oldValues[pair.Key] = pair.Value;
        var oldStructures = new Dictionary<string, List<Layer>>();
        if (structures != null) foreach (var pair in structures) oldStructures[pair.Key] = CloneLayers(pair.Value);
        try
        {
            if (target != ActivePack && !Apply(target)) throw new ArgumentException("无法应用音色包");
            foreach (var pair in changes)
            {
                var parts = pair.Key.Split('|');
                if (!Set(parts[0], int.Parse(parts[1]), parts[2], pair.Value)) throw new ArgumentException("无法应用：" + pair.Key);
            }
            if (!SaveOverrides(modRoot)) throw new IOException("保存失败，修改已回退");
        }
        catch
        {
            packOverrides[target] = oldValues;
            packStructures[target] = oldStructures;
            Apply(oldPack);
            throw;
        }
    }

    /// <summary>包载完后调用：确保导出知道目录。</summary>
    public static void FinishLoading(string modFolder)
    {
        if (!string.IsNullOrEmpty(modFolder)) modRoot = modFolder;
    }
}
