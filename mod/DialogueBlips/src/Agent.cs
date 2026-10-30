using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;
using UnityEngine;

/// <summary>
/// 文件协议的 Agent 接口（不开端口、不要网络权限）。
///
///   外部 AI 写  &lt;mod&gt;/voice-request.json  →  模组轮询、应用、回写
///   模组写      &lt;mod&gt;/voice-state.json    →  外部读当前状态
///
/// 请求格式（id 变了才会重新应用，避免重复执行）：
/// {
///   "id": "2026-10-30T14:20:00",
///   "pack": "原版音色包",                       // 可选：按显示名切包
///   "set": { "乔治奥|0|hz": 120,                 // 可选：预设|层|参数 → 值
///            "乔治奥|0|Overtones": 0.3 },
///   "audition": "乔治奥"                         // 可选：试听一次
/// }
///
/// 状态文件包含：生效的包、预设数、改动数、已应用的请求 id。
/// </summary>
internal static class VoiceAgent
{
    const string Tag = "[DialogueBlips]";
    const string RequestFile = "voice-request.json";
    const string StateFile = "voice-state.json";
    const float PollInterval = 0.5f;

    /// <summary>面板当前正在编辑谁——由 Panel 每��更新，写进状态文件供外部读。</summary>
    internal static string FocusPreset = "";
    internal static int FocusLayer;
    internal static int FocusTier;

    static string lastRequestId = "";
    static float lastPoll;
    static bool watching;
    static string requestError = "";
    static string lastAppliedRequest = "";
    static bool initialized;
    static bool pendingState;

    public static void Reset()
    {
        watching = false; lastPoll = -99; FocusPreset = ""; initialized = false; pendingState = false;
    }

    public static void Poll()
    {
        // No request-file reads or polling clock updates while the editor is hidden.
        if (!Panel.IsOpen) return;
        if (Time.unscaledTime - lastPoll < PollInterval) return;
        lastPoll = Time.unscaledTime;

        var folder = PersonaResolver.Folder;
        if (string.IsNullOrEmpty(folder)) return;
        EnsureInitialized(folder);
        if (pendingState)
        {
            pendingState = !WriteState(folder, lastRequestId);
            if (pendingState) return;
        }

        var path = Path.Combine(folder, RequestFile);
        if (!File.Exists(path)) return;

        JObject request;
        try { request = JObject.Parse(File.ReadAllText(path)); }
        catch (Exception e)
        {
            Debug.LogWarning($"{Tag} 无法解析 {RequestFile}：{e.Message}");
            return;
        }

        if (request["id"]?.Type != JTokenType.String)
        { Debug.LogWarning($"{Tag} Agent id 必须是字符串"); return; }
        var id = (string)request["id"];
        if (id.Length > 128) { Debug.LogWarning($"{Tag} Agent id 过长"); return; }
        if (id.Length == 0 || id == lastRequestId) return;

        if (!watching)
        {
            watching = true;
            Debug.Log($"{Tag} Agent 接口就绪，监听 {RequestFile}");
        }

        requestError = "";
        try { Apply(request, id); lastAppliedRequest = id; }
        catch (Exception e)
        {
            requestError = e.Message;
            Debug.LogWarning($"{Tag} Agent 请求 {id} 已拒绝：{requestError}");
        }
        lastRequestId = id;
        pendingState = !WriteState(folder, id);
    }

    static void Apply(JObject request, string id)
    {
        var pack = (string)request["pack"];
        var audition = (string)request["audition"];
        if (request["set"] != null && !(request["set"] is JObject)) throw new ArgumentException("set 必须是对象");
        var changes = new Dictionary<string, float>(StringComparer.Ordinal);
        if (request["set"] is JObject set)
        {
            if (set.Count > 256) throw new ArgumentException("单次请求最多修改 256 项");
            foreach (var pair in set) changes[pair.Key] = VoiceValidation.Number(pair.Value, pair.Key);
        }
        VoiceBank.ApplyBatch(pack, changes, audition);
        try { Panel.RefreshBank(); }
        catch (Exception e) { Debug.LogWarning($"{Tag} 参数已保存，面板刷新失败：{e.Message}"); }
        // Playback failure must not be reported as a rejected parameter transaction.
        if (!string.IsNullOrEmpty(audition))
            try { Panel.PlayPreview(audition); }
            catch (Exception e) { Debug.LogWarning($"{Tag} 参数已保存，试听失败：{e.Message}"); }
        Debug.Log($"{Tag} Agent 请求 {id} 已应用：参数 {changes.Count} 项");
    }

    static void EnsureInitialized(string folder)
    {
        if (!initialized)
        {
            initialized = true;
            lastRequestId = ""; lastAppliedRequest = ""; requestError = "";
            try
            {
                var oldPath = Path.Combine(folder, StateFile);
                if (File.Exists(oldPath))
                {
                    var old = JObject.Parse(File.ReadAllText(oldPath));
                    lastRequestId = (string)old["lastRequest"] ?? "";
                    lastAppliedRequest = (string)old["lastAppliedRequest"] ?? lastRequestId;
                    requestError = (string)old["requestError"] ?? "";
                }
            }
            catch (Exception e) { Debug.LogWarning($"{Tag} 无法读取上次回执：{e.Message}"); }
        }

    }

    /// <summary>把当前状态（含面板焦点和该层全部参数）写出去。</summary>
    public static void Publish()
    {
        if (!Panel.IsOpen) return;
        var folder = PersonaResolver.Folder;
        if (!string.IsNullOrEmpty(folder))
        {
            EnsureInitialized(folder);
            pendingState = !WriteState(folder, lastRequestId);
        }
    }

    static bool WriteState(string folder, string requestId)
    {
        try
        {
            var state = new JObject
            {
                ["activePack"] = VoiceBank.ActiveDisplayName,
                ["activePackFile"] = VoiceBank.ActivePack,
                ["presets"] = VoiceBank.PresetCount,
                ["packs"] = new JArray(VoiceBank.Packs),
                ["overrides"] = VoiceBank.OverrideCount,
                ["lastRequest"] = requestId,
                ["lastAppliedRequest"] = lastAppliedRequest,
                ["requestStatus"] = requestError.Length == 0 ? "applied" : "rejected",
                ["requestError"] = requestError,
                ["updatedAt"] = DateTime.Now.ToString("yyyy-MM-ddTHH:mm:ss"),
            };

            if (!string.IsNullOrEmpty(FocusPreset))
            {
                state["focus"] = new JObject
                {
                    ["preset"] = FocusPreset,
                    ["layer"] = FocusLayer,
                    ["layerCount"] = VoiceBank.LayerCount(FocusPreset),
                    ["tier"] = FocusTier,
                };
                var values = new JObject();
                foreach (var pair in VoiceBank.LayerParams(FocusPreset, FocusLayer))
                    values[pair.Key] = pair.Value;
                state["focusParams"] = values;
            }
            AtomicFile.Write(Path.Combine(folder, StateFile), state.ToString());
            return true;
        }
        catch (Exception e)
        {
            Debug.LogWarning($"{Tag} 写 {StateFile} 失败：{e.Message}");
            return false;
        }
    }
}
