using System;
using Newtonsoft.Json.Linq;
using Wikman.Synthesizer.Sfxr;

// All game-side pack, override and Agent writes share these limits.
internal static class VoiceValidation
{
    internal const string GameBuild = "26284217";

    internal static float Number(JToken node, string path)
    {
        if (node == null || (node.Type != JTokenType.Float && node.Type != JTokenType.Integer))
            throw new ArgumentException(path + ": 必须是数字");
        var value = (float)node;
        if (float.IsNaN(value) || float.IsInfinity(value)) throw new ArgumentException(path + ": 必须是有限数");
        return value;
    }

    internal static void Value(string slot, float value)
    {
        if (float.IsNaN(value) || float.IsInfinity(value)) throw new ArgumentException(slot + ": 必须是有限数");
        float min, max;
        switch (slot)
        {
            case "hz": min = 40; max = 3000; break;
            case "gain": min = 0; max = 1.5f; break;
            case "delay": min = 0; max = 120; break;
            default:
                ParameterData data = null;
                foreach (var item in ParameterDatabase.database)
                    if (item.parameterType.ToString() == slot && item.parameterType != ParameterType.StartFrequency) data = item;
                if (data == null) throw new ArgumentException("未知参数：" + slot);
                min = data.minimum;
                max = slot == "WaveType" ? 11 : data.maximum;
                break;
        }
        if (value < min || value > max || (slot == "WaveType" && value != Math.Truncate(value)))
            throw new ArgumentException($"{slot}: 超出范围 {min}..{max}，波形必须为整数");
    }

    internal static void Layer(JObject node, string path)
    {
        if (node == null || node.Count != 5) throw new ArgumentException(path + ": 层字段必须为 hz/gain/delay/mute/p");
        foreach (var slot in new[] { "hz", "gain", "delay" }) Value(slot, Number(node[slot], path + "/" + slot));
        if (node["mute"]?.Type != JTokenType.Boolean) throw new ArgumentException(path + "/mute: 必须是布尔值");
        var p = node["p"] as JObject;
        if (p == null || p.Count != 31) throw new ArgumentException(path + "/p: 需要完整 31 项参数");
        foreach (var item in ParameterDatabase.database)
        {
            if (item.parameterType == ParameterType.StartFrequency) continue;
            var slot = item.parameterType.ToString();
            Value(slot, Number(p[slot], path + "/p/" + slot));
        }
    }

    internal static void Layers(JToken node, string path)
    {
        var layers = node as JArray;
        if (layers == null || layers.Count < 1 || layers.Count > 8) throw new ArgumentException(path + ": 需要 1..8 层");
        for (var i = 0; i < layers.Count; i++) Layer(layers[i] as JObject, path + "/" + i);
    }

    internal static void Pack(JObject doc)
    {
        if ((string)doc["format"] != "dsp-voicepack/1") throw new ArgumentException("不支持的音色包格式");
        var requires = doc["requires"] as JObject;
        if (requires == null || Number(requires["paramCount"], "requires/paramCount") != 31)
            throw new ArgumentException("参数表版本不兼容，需要 paramCount=31");
        if (requires["gameBuild"] != null && (string)requires["gameBuild"] != GameBuild)
            throw new ArgumentException("游戏版本不兼容，需要 gameBuild=" + GameBuild);
        var presets = doc["presets"] as JObject;
        if (presets == null || presets.Count < 1 || presets.Count > 64) throw new ArgumentException("需要 1..64 个预设");
        foreach (var pair in presets)
        {
            if (string.IsNullOrWhiteSpace(pair.Key) || pair.Key.Length > 80 || pair.Key.Contains("|"))
                throw new ArgumentException("非法预设名称：" + pair.Key);
            Layers(pair.Value, "presets/" + pair.Key);
        }
        var mapping = doc["mapping"] as JObject;
        if (mapping == null) throw new ArgumentException("mapping 必须是对象");
        foreach (var pair in mapping)
            if (pair.Value.Type != JTokenType.String || presets[(string)pair.Value] == null)
                throw new ArgumentException("mapping/" + pair.Key + ": 目标预设不存在");
    }
}
