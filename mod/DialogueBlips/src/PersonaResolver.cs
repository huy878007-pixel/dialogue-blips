using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using UnityEngine;

/// <summary>
/// 把游戏里的顾客认成"哪个人物"。
///
/// 不用 identifier：一个角色有十几个（georgio1..georgio12 / abby1..abby5）。
/// 不用 displayName 当键：那是本地化字符串，切语言就变。
///
/// 做法：用本地化 key（name_xxx）做稳定身份，
/// 启动时调 LocHelper.GetLocalizedClientName(key) 现算出当前语言下的显示名，
/// 和 storeClient.displayName 比对 —— 语言无关且精确。
/// 撞名时退化到 spriteName，再退化到"通用音色 + 性别/语域"。
/// </summary>
internal static class PersonaResolver
{
    sealed class CharacterEntry
    {
        public string key;
        public List<string> nameKeys;
        public string zh;
        public string preset;
        public string tier;
        public List<string> spriteNames;
    }

    sealed class CharactersDoc
    {
        public string format;
        public Dictionary<string, Dictionary<string, string>> generic;
        public List<CharacterEntry> characters;
    }

    // 现算出来的"本语言显示名 -> 人物键"，以及反向查用到的表
    static readonly Dictionary<string, CharacterEntry> byDisplayName = new Dictionary<string, CharacterEntry>(StringComparer.Ordinal);
    static readonly Dictionary<string, CharacterEntry> bySprite = new Dictionary<string, CharacterEntry>(StringComparer.OrdinalIgnoreCase);
    static readonly Dictionary<string, CharacterEntry> byKey = new Dictionary<string, CharacterEntry>(StringComparer.OrdinalIgnoreCase);
    static readonly Dictionary<string, string> genericPreset = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
    static readonly HashSet<string> ambiguousNames = new HashSet<string>(StringComparer.Ordinal);
    static float nextNameRefresh;
    static string cachedModId;
    static bool loadAttempted;
    static bool loaded;

    public static bool Loaded => loaded;

    /// <summary>本模组目录（拿到后缓存，供 VoiceBank 读 packs）。</summary>
    public static string Folder { get; private set; }

    static bool folderNotified;

    /// <summary>目录首次解析成功时触发一次：工坊版在 Init 阶段还拿不到目录，
    /// 音色包要等这里回调之后再加载。</summary>
    public static event Action<string> FolderReady;

    /// <summary>惰性加载：Init 阶段 ModLoader.Mods 可能还没登记本模组，拿不到目录。
    /// 所以推迟到 OnEnable 或第一次真正要用的时候再试。</summary>
    public static void EnsureLoaded(string modId)
    {
        if (modId != null) cachedModId = modId;
        if (loaded || loadAttempted) return;
        Load(cachedModId);
    }

    public static void Load(string modId)
    {
        if (!string.IsNullOrEmpty(modId)) cachedModId = modId;
        modId = cachedModId;
        loadAttempted = true;
        var folder = ResolveFolder(modId);
        if (folder == null)
        {
            loadAttempted = false;
            Debug.LogWarning("[DialogueBlips] 拿不到 Mod 目录，下次解析重试");
            return;
        }
        CharactersDoc doc;
        try
        {
            doc = JsonConvert.DeserializeObject<CharactersDoc>(File.ReadAllText(Path.Combine(folder, "characters.json")));
            if (doc?.format != "dsp-characters/1" || doc.characters == null) throw new ArgumentException("人物表格式错误");
            var keys = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var entry in doc.characters)
                if (entry == null || string.IsNullOrWhiteSpace(entry.key) || string.IsNullOrWhiteSpace(entry.preset) || !keys.Add(entry.key))
                    throw new ArgumentException("人物表含空字段或重复角色键");
        }
        catch (Exception e)
        {
            Debug.LogWarning("[DialogueBlips] 人物表读取失败，保留原表：" + e.Message);
            loadAttempted = loaded;
            return;
        }
        Folder = folder;
        if (!folderNotified) { folderNotified = true; FolderReady?.Invoke(folder); }
        bySprite.Clear(); byKey.Clear(); genericPreset.Clear();
        foreach (var pair in doc.generic ?? new Dictionary<string, Dictionary<string, string>>())
            if (pair.Value != null)
                foreach (var inner in pair.Value) genericPreset[pair.Key + "|" + inner.Key] = inner.Value;
        foreach (var entry in doc.characters)
        {
            byKey[entry.key] = entry;
            foreach (var sprite in entry.spriteNames ?? new List<string>())
                if (!string.IsNullOrEmpty(sprite)) bySprite[sprite] = entry;
        }
        loaded = true;
        RefreshNames();
        Debug.Log($"[DialogueBlips] 人物表载入 {folder}：{byKey.Count} 个角色，{byDisplayName.Count} 个显示名，{bySprite.Count} 个 sprite，{genericPreset.Count} 组通用");
    }

    static void RefreshNames()
    {
        nextNameRefresh = Time.unscaledTime + 0.5f;
        byDisplayName.Clear(); ambiguousNames.Clear();
        foreach (var entry in byKey.Values)
            foreach (var key in entry.nameKeys ?? new List<string>())
            {
                var display = SafeLocalizedName(key);
                if (string.IsNullOrEmpty(display) || ambiguousNames.Contains(display)) continue;
                if (byDisplayName.TryGetValue(display, out var existing) && !ReferenceEquals(existing, entry))
                { byDisplayName.Remove(display); ambiguousNames.Add(display); }
                else byDisplayName[display] = entry;
            }
    }

    static string ResolveFolder(string modId)
    {
        if (string.IsNullOrEmpty(modId)) return null;
        try
        {
            var viaHelper = ModHelper.GetModFolder(modId);
            if (!string.IsNullOrEmpty(viaHelper) && System.IO.Directory.Exists(viaHelper)) return viaHelper;
        }
        catch { /* 忽略，走兜底 */ }

        // 兜底：<游戏目录>/Mods/<id>（Application.dataPath 是 ...\Probably Stolen_Data）
        try
        {
            var guess = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "Mods", modId));
            if (System.IO.Directory.Exists(guess)) return guess;
        }
        catch { /* 忽略 */ }

        // 兜底：工坊目录 <steamapps>/workshop/content/<appid>/<itemid>
        // 工坊版的目录不在 Mods/ 下，ModHelper 在 Init 阶段也可能还没登记。
        try
        {
            var steamapps = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", ".."));
            var root = Path.Combine(steamapps, "workshop", "content", "4348910");
            if (System.IO.Directory.Exists(root))
                foreach (var dir in System.IO.Directory.GetDirectories(root))
                {
                    var manifest = Path.Combine(dir, "manifest.xml");
                    if (System.IO.File.Exists(manifest) &&
                        System.IO.File.ReadAllText(manifest).Contains("<ID>" + modId + "</ID>"))
                        return dir;
                }
        }
        catch { /* 忽略 */ }
        return null;
    }

    static string SafeLocalizedName(string key)
    {
        try { return LocHelper.GetLocalizedClientName(key); }
        catch { return null; }
    }

    /// <summary>当前正在对话的顾客。拿不到就返回 null。</summary>
    static StoreClient CurrentClient()
    {
        try
        {
            var instance = PlayerStore.Instance;
            var client = instance == null ? null : instance.currentClientInstance;
            return client == null ? null : client.GetClientBlueprint();
        }
        catch { return null; }
    }

    /// <summary>解析结果：预设名 + 人类可读的来源说明。</summary>
    public static bool TryResolve(out string preset, out string why)
    {
        preset = null;
        why = "未解析";

        EnsureLoaded(null);
        if (loaded && Time.unscaledTime >= nextNameRefresh) RefreshNames();

        var client = CurrentClient();
        if (client == null)
        {
            why = "没有当前顾客";
            return false;
        }

        var display = client.displayName ?? "";

        // 1) 显示名精确匹配（语言无关）
        if (loaded && byDisplayName.TryGetValue(display, out var byName))
        {
            preset = VoiceBank.MappedPreset(byName.key, byName.preset);
            why = $"具名「{byName.zh}」←显示名";
            if (VoiceBank.Contains(preset)) return true;
        }

        // 2) spriteName
        var sprite = client.spriteName ?? "";
        if (loaded && sprite.Length > 0 && bySprite.TryGetValue(sprite, out var bySp))
        {
            preset = VoiceBank.MappedPreset(bySp.key, bySp.preset);
            why = $"具名「{bySp.zh}」←sprite:{sprite}";
            if (VoiceBank.Contains(preset)) return true;
        }

        // 3) identifier —— 实测很多具名角色直接用名字当 identifier（导师 = "mentor"），
        //    而剧情分支会加后缀（georgio1 / abby3 / georgioSerpicoLetter），所以去尾数字再比。
        var id = client.identifier ?? "";
        if (loaded && id.Length > 0 && byKey.TryGetValue(id, out var byId))
        {
            preset = VoiceBank.MappedPreset(byId.key, byId.preset);
            why = $"具名「{byId.zh}」←identifier:{id}";
            if (VoiceBank.Contains(preset)) return true;
        }
        var trimmed = TrimTrailingDigits(id);
        if (loaded && trimmed.Length > 0 && trimmed != id && byKey.TryGetValue(trimmed, out var byTrim))
        {
            preset = VoiceBank.MappedPreset(byTrim.key, byTrim.preset);
            why = $"具名「{byTrim.zh}」←identifier:{id}→{trimmed}";
            if (VoiceBank.Contains(preset)) return true;
        }

        // 4) 通用音色：性别 × 语域
        try
        {
            var gender = LocGenderHelper.GetClientGender(client).ToString().ToUpperInvariant();
            var register = LocGenderHelper.GetClientRegister(client).ToString().ToUpperInvariant();
            if (genericPreset.TryGetValue(gender + "|" + register, out var generic))
            {
                preset = VoiceBank.MappedPreset(gender + "|" + register, generic);
                why = $"通用「{generic}」←{gender}/{register}";
                return true;
            }
            if (genericPreset.TryGetValue("NEUTRAL|" + register, out var fallback))
            {
                preset = VoiceBank.MappedPreset("NEUTRAL|" + register, fallback);
                why = $"通用兜底「{fallback}」←NEUTRAL/{register}";
                return true;
            }
            why = $"通用表里没有 {gender}/{register}（loaded={loaded}, 组合数={genericPreset.Count}）";
        }
        catch (Exception e)
        {
            why = "性别/语域取不到：" + e.Message;
        }

        return false;
    }


    /// <summary>
    /// 给面板用的角色表。**通用音色排最前面**——它们覆盖约 110 个原型角色，
    /// 是玩家最常听到的四个，不该藏在具名角色后面。
    /// </summary>
    public static List<(string zh, string preset, string tier)> All()
    {
        var list = new List<(string, string, string)>();
        var seen = new HashSet<string>(StringComparer.Ordinal);

        foreach (var preset in GenericOrder())
            if (seen.Add(preset)) list.Add((preset, preset, "通用"));

        var named = new List<(string, string, string)>();
        foreach (var entry in byKey.Values)
        {
            var preset = VoiceBank.MappedPreset(entry.key, entry.preset);
            if (seen.Add(preset)) named.Add((entry.zh, preset, entry.tier ?? ""));
        }
        named.Sort((a, b) => string.CompareOrdinal(a.Item1, b.Item1));
        list.AddRange(named);
        return list;
    }

    /// <summary>通用展示顺序：男普通 → 男老成 → 女年轻 → 女成熟；包里多出来的排后面。</summary>
    static List<string> GenericOrder()
    {
        var preferred = new List<string> { "男年轻", "男老", "女年轻", "女老年" };
        var present = new List<string>();
        foreach (var pair in genericPreset)
        {
            var preset = VoiceBank.MappedPreset(pair.Key, pair.Value);
            if (!present.Contains(preset)) present.Add(preset);
        }

        var ordered = new List<string>();
        foreach (var name in preferred)
            if (present.Contains(name)) ordered.Add(name);
        foreach (var name in present)
            if (!ordered.Contains(name)) ordered.Add(name);
        return ordered;
    }

    static string TrimTrailingDigits(string value)
    {
        if (string.IsNullOrEmpty(value)) return value ?? "";
        var end = value.Length;
        while (end > 0 && char.IsDigit(value[end - 1])) end--;
        return value.Substring(0, end);
    }

    /// <summary>日志用的一句话描述。</summary>
    public static string Describe(string slot)
    {
        if (slot == "player") return "玩家";
        if (slot == "sec") return "保安";

        var client = CurrentClient();
        var name = client == null ? "?" : client.displayName;
        var id = client == null ? "?" : client.identifier;
        if (TryResolve(out var preset, out var why))
            return $"{name} → {preset}  ({why})";
        return $"{name}({id}) → ?  ({why})";
    }
}
