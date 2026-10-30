using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using Wikman.Synthesizer.Sfxr;

// One shared console document. Audio rendering continues to use the existing endpoints.
internal sealed class ConsoleState
{
    readonly object gate = new();
    readonly string file = Environment.GetEnvironmentVariable("BLIP_STATE_PATH") ??
        Path.Combine(AppContext.BaseDirectory, "console-state.json");
    JsonObject snapshot;

    public ConsoleState()
    {
        var p = Program.VoiceParams(Program.VoiceIndex("female_young"));
        p.Remove(ParameterType.StartFrequency);
        snapshot = Wrap(new JsonObject
        {
            ["layers"] = new JsonArray(new JsonObject
            {
                ["hz"] = 1056, ["gain"] = 1, ["delay"] = 0, ["mute"] = false,
                ["p"] = JsonSerializer.SerializeToNode(p),
            }),
            ["sentence"] = new JsonObject
            {
                ["text"] = "这批货来路不太干净，你最好给我个说法。",
                ["interval"] = 30, ["throttle"] = 55, ["jitter"] = 6,
            },
            ["autoplay"] = true, ["previewMode"] = "single", ["selectedPreset"] = "女年轻",
        }, 0, "initial");
        if (!File.Exists(file)) return;
        try
        {
            var loaded = JsonNode.Parse(File.ReadAllText(file)) as JsonObject;
            Keys(loaded, new[] { "revision", "source", "updatedAt", "state" });
            Validate(loaded?["state"] as JsonObject);
            var revision = Number(loaded["revision"], 0, 9007199254740991);
            if (revision != Math.Truncate(revision)) throw new ArgumentException("Invalid revision.");
            Text(loaded["source"], 40);
            Text(loaded["updatedAt"], 80);
            snapshot = loaded;
        }
        catch (Exception e) when (e is JsonException || e is ArgumentException || e is InvalidOperationException)
        {
            // Preserve a damaged saved document before a later successful edit can replace it.
            File.Copy(file, file + ".invalid-" + DateTime.UtcNow.ToString("yyyyMMddHHmmssfff"));
            Console.Error.WriteLine("[state] Saved document was invalid; preserved a copy: " + e.Message);
        }
    }

    static JsonObject Wrap(JsonObject state, long revision, string source) => new()
    {
        ["revision"] = revision, ["source"] = source,
        ["updatedAt"] = DateTime.UtcNow.ToString("O"), ["state"] = state,
    };

    public string Read()
    {
        lock (gate) return snapshot.ToJsonString();
    }

    public (int status, string json) Update(string body, bool isPatch)
    {
        var request = JsonNode.Parse(body) as JsonObject ?? throw new ArgumentException("Expected a JSON object.");
        Keys(request, isPatch ? new[] { "baseRevision", "source", "patch" } : new[] { "baseRevision", "source", "state" });
        var source = Text(request["source"], 40);
        var revisionNumber = Number(request["baseRevision"], 0, 9007199254740991);
        if (revisionNumber != Math.Truncate(revisionNumber)) throw new ArgumentException("baseRevision must be an integer.");
        lock (gate)
        {
            if (revisionNumber != snapshot["revision"].GetValue<long>()) return (409, snapshot.ToJsonString());
            var state = isPatch ? snapshot["state"].DeepClone() as JsonObject : request["state"]?.DeepClone() as JsonObject;
            if (isPatch)
            {
                var operations = request["patch"] as JsonArray;
                if (operations == null || operations.Count < 1 || operations.Count > 64)
                    throw new ArgumentException("patch must contain 1 to 64 replace operations.");
                foreach (var node in operations) Replace(state, node as JsonObject);
            }
            Validate(state);
            // An edit to the active stack is also an edit to its named voice.
            // Keep API clients, the browser and persisted documents consistent.
            if (isPatch)
            {
                var changedLayers = false;
                foreach (var node in (JsonArray)request["patch"])
                {
                    var path = node["path"].GetValue<string>();
                    if (path == "/layers" || path.StartsWith("/layers/")) changedLayers = true;
                }
                var selected = state["selectedPreset"].GetValue<string>();
                if (changedLayers && selected.Length > 0)
                {
                    if (state["presets"] == null) state["presets"] = new JsonObject();
                    state["presets"][selected] = state["layers"].DeepClone();
                    Validate(state);
                }
            }
            var next = Wrap(state, snapshot["revision"].GetValue<long>() + 1, source);
            var json = next.ToJsonString();
            var directory = Path.GetDirectoryName(Path.GetFullPath(file));
            Directory.CreateDirectory(directory);
            File.WriteAllText(file + ".tmp", json);
            File.Move(file + ".tmp", file, true);
            snapshot = next;
            return (200, json);
        }
    }

    static void Replace(JsonObject state, JsonObject operation)
    {
        Keys(operation, new[] { "op", "path", "value" });
        if (Text(operation["op"], 12) != "replace") throw new ArgumentException("Only replace operations are supported.");
        var path = Text(operation["path"], 120);
        if (!path.StartsWith('/') || path.Contains('~')) throw new ArgumentException("Invalid parameter path.");
        var parts = path[1..].Split('/');
        JsonNode current = state;
        for (var i = 0; i < parts.Length; i++)
        {
            var key = parts[i];
            if (current is JsonObject obj && obj.ContainsKey(key))
            {
                if (i == parts.Length - 1) { obj[key] = operation["value"]?.DeepClone(); return; }
                current = obj[key];
            }
            else if (current is JsonArray array && int.TryParse(key, out var index) && index >= 0 && index < array.Count)
            {
                if (i == parts.Length - 1) { array[index] = operation["value"]?.DeepClone(); return; }
                current = array[index];
            }
            else throw new ArgumentException("Unknown parameter path: " + path);
        }
    }

    static void Validate(JsonObject state)
    {
        // "presets" is optional so documents saved before it existed still load.
        var required = new[] { "layers", "sentence", "autoplay", "previewMode", "selectedPreset" };
        if (state == null || state.Count < required.Length || state.Count > required.Length + 1)
            throw new ArgumentException("Unexpected or missing fields.");
        foreach (var key in state)
            if (key.Key != "presets" && Array.IndexOf(required, key.Key) < 0)
                throw new ArgumentException("Unexpected field: " + key.Key);
        foreach (var name in required)
            if (!state.ContainsKey(name)) throw new ArgumentException("Missing field: " + name);

        var db = new ParameterDatabase();
        var defaults = Program.DefaultParams();
        defaults.Remove(ParameterType.StartFrequency);

        void ValidateLayer(JsonObject layer)
        {
            Keys(layer, new[] { "hz", "gain", "delay", "mute", "p" });
            Number(layer["hz"], 40, 3000);
            Number(layer["gain"], 0, 1.5);
            Number(layer["delay"], 0, 120);
            Boolean(layer["mute"]);
            var p = layer["p"] as JsonObject;
            if (p == null || p.Count != defaults.Count) throw new ArgumentException("Expected a complete synthesis parameter table.");
            foreach (var parameter in defaults.Keys)
            {
                var value = Number(p[parameter.ToString()], db.GetMin(parameter),
                    parameter == ParameterType.WaveType ? 11 : db.GetMax(parameter));
                if (parameter == ParameterType.WaveType && value != Math.Truncate(value))
                    throw new ArgumentException("WaveType must be an integer.");
            }
        }

        void ValidateLayerArray(JsonArray array, string what)
        {
            if (array == null || array.Count < 1 || array.Count > 8) throw new ArgumentException($"Expected 1 to 8 layers in {what}.");
            foreach (var node in array) ValidateLayer(node as JsonObject);
        }

        ValidateLayerArray(state["layers"] as JsonArray, "the active stack");

        // Per-preset overrides: a preset whose parameters the player edited becomes theirs.
        if (state.ContainsKey("presets") && state["presets"] is not JsonObject)
            throw new ArgumentException("presets must be an object.");
        if (state["presets"] is JsonObject presets)
        {
            if (presets.Count > 64) throw new ArgumentException("Too many saved presets.");
            foreach (var entry in presets)
            {
                if (entry.Key.Length > 80) throw new ArgumentException("Preset name too long.");
                ValidateLayerArray(entry.Value as JsonArray, "preset '" + entry.Key + "'");
            }
        }

        var sentence = state["sentence"] as JsonObject;
        Keys(sentence, new[] { "text", "interval", "throttle", "jitter" });
        var text = Text(sentence["text"], 512);
        var interval = Number(sentence["interval"], 10, 90);
        Number(sentence["throttle"], 20, 200);
        Number(sentence["jitter"], 0, 25);
        var duration = 0.0;
        foreach (var ch in text)
            duration += char.IsWhiteSpace(ch) ? interval / 2000 : char.IsPunctuation(ch) ? .32 :
                char.IsLowSurrogate(ch) ? 0 : interval / 1000;
        if (duration > 60) throw new ArgumentException("Sentence preview exceeds 60 seconds.");
        Boolean(state["autoplay"]);
        if (Text(state["previewMode"], 12) is not ("single" or "sentence"))
            throw new ArgumentException("previewMode must be single or sentence.");
        Text(state["selectedPreset"], 80);
    }

    static void Keys(JsonObject obj, string[] keys)
    {
        if (obj == null || obj.Count != keys.Length) throw new ArgumentException("Unexpected or missing fields.");
        foreach (var key in keys)
            if (!obj.ContainsKey(key)) throw new ArgumentException("Missing field: " + key);
    }
    static double Number(JsonNode node, double min, double max)
    {
        if (node?.GetValueKind() != JsonValueKind.Number) throw new ArgumentException("Expected a number.");
        var value = node.Deserialize<double>();
        if (!double.IsFinite(value) || value < min || value > max)
            throw new ArgumentException($"Expected a finite value in [{min.ToString(CultureInfo.InvariantCulture)}, {max.ToString(CultureInfo.InvariantCulture)}].");
        return value;
    }
    static string Text(JsonNode node, int max)
    {
        if (node?.GetValueKind() != JsonValueKind.String) throw new ArgumentException("Expected text.");
        var text = node.GetValue<string>();
        if (text.Length > max) throw new ArgumentException($"Text exceeds {max} characters.");
        return text;
    }
    static void Boolean(JsonNode node)
    {
        if (node?.GetValueKind() is not (JsonValueKind.True or JsonValueKind.False))
            throw new ArgumentException("Expected a boolean.");
    }
}
