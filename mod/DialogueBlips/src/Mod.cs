using System;
using System.Collections.Generic;
using Febucci.UI;
using Febucci.UI.Core;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.SceneManagement;

/// <summary>
/// 对话逐字语音。
///
/// 已验证（2026-10-30 真实运行）：
///   · DialogUIManager 的 client / player / sec 三个气泡都能收到 onCharacterVisible
///   · 人物识别四层链有效：显示名 → spriteName → identifier → 性别/语域通用音色
///   · 游戏原生的打字机音效是场景里独立的「Typewriter Audio Source」，
///     clip 名「Typewriter sound 1」，音量跟随 dialogVolume
/// </summary>
public class DialogueBlipsMod : IMod
{
    const string Tag = "[DialogueBlips]";

    ModManifest manifest;

    /// <summary>面板要直接调这两个音量，所以做成可访问的静态引用。</summary>
    internal static ConfigEntry<float> VolumeGain;
    internal static ConfigEntry<float> NativeVolume;
    internal static ConfigEntry<int> ThrottleMs;



    readonly Dictionary<TypewriterCore, UnityAction<char>> bound = new Dictionary<TypewriterCore, UnityAction<char>>();
    bool enabled;
    /// <summary>游戏原生的打字机音源（三个气泡可能各有一份）。</summary>
    readonly List<AudioSource> nativeSources = new List<AudioSource>();

    readonly Dictionary<AudioSource, float> originalNativeVolumes = new Dictionary<AudioSource, float>();

    internal static DialogueBlipsMod Current;
    AudioSource source;
    GameObject host;

    string lastPersona = "";
    float lastPlayed = -99f;
    int charCount;

    // ---------------------------------------------------------------- 生命周期
    public void Init(ModManifest manifest)
    {
        this.manifest = manifest;
        Current = this;
        Debug.Log($"{Tag} init {manifest.ID} v{manifest.ModVersion}");

        var config = ModConfig.For(manifest.ID);
        // 我们走的是「对话音量」滑条（dialogVolume），默认值只有一半，
        // 而原生打字机音效也用它，所以给个增益方便对齐听感。
        VolumeGain = config.Define("volume", 2.0f, "音效", () => "对话音效音量增益", 0f, 3f,
            () => "在游戏的「对话音量」基础上再乘这一档。");
        ThrottleMs = config.Define("throttle", 55, "音效", () => "最短发声间隔 (ms)", 20, 200,
            () => "两次发声之间至少隔多久。越小越密。");
        // 用户定的是滑块不是开关：0 = 只有角色语音，1 = 保留游戏原样。
        NativeVolume = config.Define("native_volume", 0f, "音效", () => "原生打字机音效音量", 0f, 1f,
            () => "游戏自带的打字机咔哒声。0 = 只留角色语音；1 = 游戏原样；中间值按比例混合。");
        NativeVolume.OnChanged += _ => { if (enabled) ApplyNativeVolume(); };
        VolumeGain.OnChanged += _ => { if (enabled) ReapplyAudio(); };
    }

    public void OnEnable()
    {
        if (enabled) return;
        enabled = true;
        Current = this;
        SceneManager.sceneLoaded += OnSceneLoaded;
        PersonaResolver.EnsureLoaded(manifest?.ID);
        if (PersonaResolver.Loaded)
        {
            VoiceBank.Load(PersonaResolver.Folder);
            VoiceBank.FinishLoading(PersonaResolver.Folder);
        }
        EnsureSource();
        ReapplyAudio();
        Bind();
        Debug.Log($"{Tag} enabled");
    }

    public void OnDisable()
    {
        if (!enabled) return;
        enabled = false;
        Panel.Shutdown();
        VoiceAgent.Reset();
        if (source != null) source.Stop();
        SceneManager.sceneLoaded -= OnSceneLoaded;
        UnbindAll();
        RestoreNativeVolumes();
        VoiceBank.ReleasePools();
        if (host != null) UnityEngine.Object.Destroy(host);
        host = null;
        source = null;
        if (Current == this) Current = null;
        Debug.Log($"{Tag} disabled");
    }

    void OnSceneLoaded(Scene scene, LoadSceneMode mode)
    {
        UnbindAll();
        RestoreNativeVolumes();
        ApplyNativeVolume();
        Bind();
    }

    // ---------------------------------------------------------------- 音频
    void EnsureSource()
    {
        if (source != null) return;
        host = new GameObject("DialogueBlipsAudio");
        UnityEngine.Object.DontDestroyOnLoad(host);
        host.AddComponent<PanelHotkey>();   // F11 开面板（IMod 没有 Update）
        source = host.AddComponent<AudioSource>();
        source.playOnAwake = false;
        source.loop = false;
        source.spatialBlend = 0f;
        source.volume = CurrentVolume();
    }

    internal static float DialogVolume()
    {
        try { return Mathf.Clamp01(EmporiumOption.Instance != null ? EmporiumOption.Instance.dialogVolume : 0.7f); }
        catch { return 0.7f; }
    }

    internal static float GainLimit => DialogVolume() > 0 ? Mathf.Min(3f, 1f / DialogVolume()) : 3f;

    internal float CurrentVolume()
    {
        var baseVolume = 0.7f;
        try
        {
            if (EmporiumOption.Instance != null) baseVolume = EmporiumOption.Instance.dialogVolume;
        }
        catch { /* 菜单场景拿不到就用默认 */ }
        return Mathf.Clamp01(baseVolume * (VolumeGain == null ? 2f : Mathf.Clamp(VolumeGain.Value, 0, GainLimit)));
    }

    float ThrottleSecondsNow()
    {
        return (ThrottleMs == null ? 55 : Mathf.Clamp(ThrottleMs.Value, 20, 200)) / 1000f;
    }

    // ---------------------------------------------------------------- 原生打字机
    /// <summary>按 clip 名（或节点名）以 Typewriter 开头匹配，改名也不怕。</summary>
    void RefreshNativeSources()
    {
        nativeSources.RemoveAll(audio => audio == null);
        foreach (var audio in UnityEngine.Object.FindObjectsOfType<AudioSource>(true))
        {
            if (audio == null || nativeSources.Contains(audio)) continue;
            var clipName = audio.clip != null ? audio.clip.name : "";
            if (!clipName.StartsWith("Typewriter", StringComparison.OrdinalIgnoreCase)
                && !audio.name.StartsWith("Typewriter", StringComparison.OrdinalIgnoreCase)) continue;
            nativeSources.Add(audio);
            if (!originalNativeVolumes.ContainsKey(audio)) originalNativeVolumes[audio] = audio.volume;
            Debug.Log($"{Tag} 锁定原生打字机音源「{audio.name}」clip={clipName}");
        }
    }

    /// <summary>面板改完音量后调用：立刻生效，不用等下一句对话。</summary>
    internal static void ReapplyAudio()
    {
        if (Current == null || !Current.enabled) return;
        Current.ApplyNativeVolume();
        Panel.ReapplyAudio();
        if (Current.source != null) Current.source.volume = Current.CurrentVolume();
    }

    void RestoreNativeVolumes()
    {
        foreach (var pair in originalNativeVolumes)
            if (pair.Key != null) pair.Key.volume = pair.Value;
        originalNativeVolumes.Clear();
        nativeSources.Clear();
    }

    void ApplyNativeVolume()
    {
        if (!enabled) return;
        try
        {
            RefreshNativeSources();
            if (nativeSources.Count == 0) return;
            var baseVolume = 0.7f;
            if (EmporiumOption.Instance != null) baseVolume = EmporiumOption.Instance.dialogVolume;
            var target = Mathf.Clamp01(baseVolume * (NativeVolume == null ? 0f : Mathf.Clamp01(NativeVolume.Value)));
            foreach (var audio in nativeSources)
                if (audio != null) audio.volume = target;
        }
        catch (Exception e)
        {
            Debug.LogWarning($"{Tag} 调整原生打字机音量失败：{e.Message}");
        }
    }

    // ---------------------------------------------------------------- 绑定
    void Bind()
    {
        var managers = UnityEngine.Object.FindObjectsOfType<DialogUIManager>(true);
        if (managers == null) return;
        foreach (var manager in managers)
        {
            Subscribe(manager, "client", manager.clientBubble);
            Subscribe(manager, "player", manager.playerBubble);
            Subscribe(manager, "sec", manager.secBubble);
        }
    }

    void Subscribe(DialogUIManager owner, string slot, TextBubble bubble)
    {
        if (owner == null || bubble == null || bubble.typewriter == null) return;
        var typewriter = bubble.typewriter;
        if (bound.ContainsKey(typewriter)) return;
        UnityAction<char> handler = ch => OnCharacter(slot, ch);
        bound[typewriter] = handler;
        typewriter.onCharacterVisible.AddListener(handler);
        Debug.Log($"{Tag} 已绑定 {slot} 气泡");
    }

    void UnbindAll()
    {
        foreach (var pair in bound)
            if (pair.Key != null) pair.Key.onCharacterVisible.RemoveListener(pair.Value);
        bound.Clear();
        lastPersona = "";
        lastPlayed = -99f;
        charCount = 0;
    }

    // ---------------------------------------------------------------- 逐字
    void OnCharacter(string slot, char character)
    {
        if (!enabled) return;
        charCount++;
        if (character == ' ' || character == '\n' || character == '\r' || character == '\t') return;
        if (char.IsPunctuation(character)) return;

        var preset = ResolvePreset(slot);
        if (preset != lastPersona)
        {
            lastPersona = preset ?? "";
            lastPlayed = -99f;          // 换人立刻允许响第一声
            ApplyNativeVolume();        // 对话 UI 此时才存在；游戏也可能重设过音量
            Panel.NoteSpeaker(preset);
            Debug.Log($"{Tag} [{slot}] → {preset ?? "（无音色）"}  chars={charCount}");
        }
        if (preset == null) return;
        if (Time.unscaledTime - lastPlayed < ThrottleSecondsNow()) return;

        var pool = VoiceBank.Pool(preset);
        if (pool == null || pool.Length == 0 || source == null) return;

        lastPlayed = Time.unscaledTime;
        source.volume = CurrentVolume();
        source.PlayOneShot(pool[UnityEngine.Random.Range(0, pool.Length)]);
    }

    static string ResolvePreset(string slot)
    {
        if (slot == "player") return "男年轻";        // 玩家暂用通用男声
        if (slot == "sec") return "男老";   // 保安走通用老成
        return PersonaResolver.TryResolve(out var preset, out _) ? preset : null;
    }
}
