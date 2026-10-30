// Drives the vendored bfxr synthesiser (src/SfxrGenerator.cs — see THIRD-PARTY-NOTICES.md).
// No DSP is reimplemented here: every sample comes out of SfxrInterface.CreateWithData.
//
//   bfxrhost            -> writes audition WAVs
//   bfxrhost serve 8731 -> serves the interactive console at http://127.0.0.1:8731/
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json;
using Wikman.Synthesizer.Sfxr;

internal static class Program
{
    const string OutDir = @"D:\AI\blip-lab\bfxr-samples";
    const int Sr = 44100;

    // bfxr maps StartFrequency -> period = 100/(f^2+0.001) sub-samples. The oscillator runs
    // 8 super-samples per output sample (see the `for (j = 0; j < 8; j++)` loop in
    // SfxrGenerator.Generate), so the real fundamental is 8 * 44100 / period:
    //     f_Hz = 3528 * (startFreq^2 + 0.001)
    // Range is roughly 3.5 Hz .. 3528 Hz.
    public static float HzToStart(float hz) => (float)Math.Sqrt(Math.Clamp(hz / 3528.0 - 0.001, 0.0, 1.0));
    public static float StartToHz(float s) => 3528f * (s * s + 0.001f);

    // ---------------------------------------------------------------- params
    public static Dictionary<ParameterType, float> DefaultParams()
    {
        var db = new ParameterDatabase();
        var p = new Dictionary<ParameterType, float>();
        foreach (ParameterType pt in Enum.GetValues(typeof(ParameterType)))
            if (pt != ParameterType.None) p[pt] = db.GetDefault(pt);
        return p;
    }

    /// <summary>Soft blip starting point: sine/triangle, bfxr low-pass engaged, short envelope.</summary>
    static Dictionary<ParameterType, float> Base(float hz)
    {
        var p = DefaultParams();
        p[ParameterType.WaveType] = 2f;          // sine
        p[ParameterType.MasterVolume] = 0.62f;
        p[ParameterType.AttackTime] = 0.05f;
        p[ParameterType.SustainTime] = 0.05f;
        p[ParameterType.SustainPunch] = 0f;
        p[ParameterType.DecayTime] = 0.15f;
        p[ParameterType.CompressionAmount] = 0f;
        p[ParameterType.StartFrequency] = HzToStart(hz);
        p[ParameterType.MinFrequency] = 0f;
        p[ParameterType.Slide] = -0.16f;
        p[ParameterType.DeltaSlide] = 0f;
        p[ParameterType.VibratoDepth] = 0f;
        p[ParameterType.VibratoSpeed] = 0.3f;
        p[ParameterType.Overtones] = 0.10f;
        p[ParameterType.OvertoneFalloff] = 0.62f;
        p[ParameterType.ChangeRepeat] = 0f;
        p[ParameterType.ChangeAmount] = 0f;
        p[ParameterType.ChangeSpeed] = 1f;
        p[ParameterType.ChangeAmount2] = 0f;
        p[ParameterType.ChangeSpeed2] = 1f;
        p[ParameterType.SquareDuty] = 0.5f;
        p[ParameterType.DutySweep] = 0f;
        p[ParameterType.RepeatSpeed] = 0f;
        p[ParameterType.FlangerOffset] = 0f;
        p[ParameterType.FlangerSweep] = 0f;
        p[ParameterType.LpFilterCutoff] = 0.60f;
        p[ParameterType.LpFilterCutoffSweep] = 0f;
        p[ParameterType.LpFilterResonance] = 0.10f;
        p[ParameterType.HpFilterCutoff] = 0f;
        p[ParameterType.HpFilterCutoffSweep] = 0f;
        p[ParameterType.BitCrush] = 0f;
        p[ParameterType.BitCrushSweep] = 0f;
        return p;
    }

    sealed class Voice
    {
        public string Key, Label;
        public float Hz;
        public Action<Dictionary<ParameterType, float>> Tune;
    }

    // Pitches below are real Hz now. Deliberately not all soft: the game has gruff
    // security types and rough scavengers too, so one preset is a growl, not a chirp.
    // 2026-10-30: 删除 "男 · 粗粝（喔喔喔）"。用户判定为"纯粹的刺耳"，不要恢复。
    // 低音区男声的需求仍在，候选见面板里的「候选D · 老男 88Hz」（深但不刺）。
    static readonly Voice[] Voices =
    {
        // 普通男：三角波。用户反馈"还行，但音量偏小" —— 拉到峰值上限并补一点中频泛音，
        // 因为 145 Hz 的能量几乎全在低频，只加增益听起来仍然轻。
        new() { Key = "male_plain", Label = "男年轻", Hz = 145f,
                Tune = p => { p[ParameterType.WaveType] = 4f; p[ParameterType.LpFilterCutoff] = 0.68f;
                              p[ParameterType.MasterVolume] = 0.85f;
                              p[ParameterType.AttackTime] = 0.03f; p[ParameterType.SustainTime] = 0.07f;
                              p[ParameterType.DecayTime] = 0.16f; p[ParameterType.Slide] = -0.12f;
                              p[ParameterType.Overtones] = 0.16f; p[ParameterType.OvertoneFalloff] = 0.60f; } },
        // 老成正式：低、稳、偏慢。用户反馈"太闷" —— 原来用正弦波，正弦没有泛音，
        // 必然发闷。改为三角波 + 打开低通 + 加泛音，保留低音区和慢包络来维持"老成"。
        new() { Key = "male_old", Label = "男老", Hz = 122f,
                Tune = p => { p[ParameterType.WaveType] = 4f; p[ParameterType.LpFilterCutoff] = 0.72f;
                              p[ParameterType.AttackTime] = 0.06f; p[ParameterType.SustainTime] = 0.10f;
                              p[ParameterType.DecayTime] = 0.20f; p[ParameterType.Slide] = -0.06f;
                              p[ParameterType.Overtones] = 0.22f; p[ParameterType.OvertoneFalloff] = 0.62f; } },
        // 年轻女：这就是你说好听的那个 —— 三角波，实际约 1 kHz，尾音下滑
        new() { Key = "female_young", Label = "女年轻", Hz = 1056f,
                Tune = p => { p[ParameterType.WaveType] = 4f; p[ParameterType.LpFilterCutoff] = 0.42f;
                              p[ParameterType.AttackTime] = 0.05f; p[ParameterType.SustainTime] = 0.07f;
                              p[ParameterType.DecayTime] = 0.18f; p[ParameterType.Slide] = -0.10f; } },
        // 成熟女：低一些，圆一些
        new() { Key = "female_mature", Label = "女老年", Hz = 620f,
                Tune = p => { p[ParameterType.WaveType] = 4f; p[ParameterType.LpFilterCutoff] = 0.55f;
                              p[ParameterType.AttackTime] = 0.04f; p[ParameterType.SustainTime] = 0.06f;
                              p[ParameterType.DecayTime] = 0.16f; p[ParameterType.Slide] = -0.16f;
                              p[ParameterType.VibratoDepth] = 0.06f; p[ParameterType.VibratoSpeed] = 0.35f; } },
        // 中性：不偏向
        new() { Key = "neutral", Label = "中性", Hz = 420f,
                Tune = p => { p[ParameterType.WaveType] = 2f; p[ParameterType.LpFilterCutoff] = 0.60f;
                              p[ParameterType.AttackTime] = 0.04f; p[ParameterType.SustainTime] = 0.05f;
                              p[ParameterType.DecayTime] = 0.15f; p[ParameterType.Slide] = -0.20f; } },
    };

    public static Dictionary<ParameterType, float> VoiceParams(int index)
    {
        var v = Voices[Math.Clamp(index, 0, Voices.Length - 1)];
        var p = Base(v.Hz);
        v.Tune(p);
        return p;
    }

    /// <summary>Voice count, so callers never hard-code the array length.</summary>
    public static int VoiceCount => Voices.Length;

    /// <summary>Look a voice up by its stable key instead of by position.
    /// Positional indices broke once already when a preset was removed.</summary>
    public static int VoiceIndex(string key)
    {
        for (var i = 0; i < Voices.Length; i++)
            if (Voices[i].Key == key) return i;
        throw new ArgumentException("Unknown voice key: " + key);
    }

    public static string PresetsJson()
    {
        var voices = new List<object>();
        for (var i = 0; i < Voices.Length; i++)
        {
            // 音高只走 hz，p 里不留 StartFrequency —— 与 /api/state 的校验契约一致。
            // 漏这一条会让"保存已编辑的预设"被 400 拒掉（p 的键数多一个）。
            var p = VoiceParams(i);
            p.Remove(ParameterType.StartFrequency);
            voices.Add(new { key = Voices[i].Key, label = Voices[i].Label, hz = Voices[i].Hz, p });
        }
        var voiceBase = Base(420);
        voiceBase.Remove(ParameterType.StartFrequency);
        return JsonSerializer.Serialize(new { voices, voiceBase });
    }

    // ------------------------------------------------------------ rendering
    public static float[] Render(Dictionary<ParameterType, float> p)
    {
        // The generator contains mutable oscillator/envelope state. Never share it across requests.
        var synth = new SfxrInterface();
        synth.CreateWithData(p, out var buffer, out _, out _);
        return buffer;
    }

    /// <summary>One synth layer of a voice. A voice is a stack of these, mixed together —
    /// e.g. a triangle body plus a quiet pink-noise layer for breath.</summary>
    public sealed class Layer
    {
        public Dictionary<ParameterType, float> Params;
        public float Gain = 1f;      // linear mix weight, independent of MasterVolume
        public float DelayMs = 0f;   // nudge this layer later in time
        public bool Mute;

        public Layer(Dictionary<ParameterType, float> p) { Params = p; }
        public Layer Clone() => new(new Dictionary<ParameterType, float>(Params))
        { Gain = Gain, DelayMs = DelayMs, Mute = Mute };
    }

    public static float[] RenderLayers(List<Layer> layers)
    {
        var parts = new List<(float[] y, int at, float gain)>();
        var len = 0;
        foreach (var l in layers)
        {
            if (l.Mute || l.Gain == 0f) continue;
            var y = Render(l.Params);
            var at = (int)(l.DelayMs / 1000f * Sr);
            if (at < 0) at = 0;
            parts.Add((y, at, l.Gain));
            len = Math.Max(len, at + y.Length);
        }
        if (len <= 0) return new float[1];
        var buf = new float[len];
        foreach (var (y, at, gain) in parts)
            for (var i = 0; i < y.Length && at + i < buf.Length; i++)
                buf[at + i] += y[i] * gain;
        return buf;
    }

    public static void Normalize(float[] y, float peakTarget)
    {
        var peak = 0f;
        foreach (var s in y) peak = Math.Max(peak, Math.Abs(s));
        if (peak <= 1e-9f) return;
        var g = peakTarget / peak;
        for (var i = 0; i < y.Length; i++) y[i] *= g;
    }

    // Preview/export should preserve gain, only attenuating signals that would clip.
    public static void LimitPeak(float[] y, float ceiling)
    {
        var peak = 0f;
        foreach (var sample in y) peak = Math.Max(peak, Math.Abs(sample));
        if (peak > ceiling) Normalize(y, ceiling);
    }

    public static byte[] ToWavBytes(float[] y)
    {
        var pcm = new byte[y.Length * 2];
        for (var i = 0; i < y.Length; i++)
        {
            var v = (short)Math.Clamp(y[i] * 32767f, -32768f, 32767f);
            pcm[i * 2] = (byte)(v & 0xFF);
            pcm[i * 2 + 1] = (byte)((v >> 8) & 0xFF);
        }
        using var ms = new MemoryStream(44 + pcm.Length);
        using var w = new BinaryWriter(ms);
        w.Write(Encoding.ASCII.GetBytes("RIFF"));
        w.Write(36 + pcm.Length);
        w.Write(Encoding.ASCII.GetBytes("WAVEfmt "));
        w.Write(16); w.Write((short)1); w.Write((short)1);
        w.Write(Sr); w.Write(Sr * 2); w.Write((short)2); w.Write((short)16);
        w.Write(Encoding.ASCII.GetBytes("data"));
        w.Write(pcm.Length);
        w.Write(pcm);
        w.Flush();
        return ms.ToArray();
    }

    /// <summary>Preview cadence: 30 ms per char, 55 ms blip throttle, 320 ms on punctuation.
    /// The throttle is tuned independently from the game's example sound writer.</summary>
    public static float[] Speak(string text, List<Layer> layers,
                                double jitter = 0.06, double throttle = 0.055,
                                double interval = 0.030, double punctPause = 0.32)
    {
        if (text == null || text.Length > 512 || !double.IsFinite(interval) || interval <= 0 ||
            !double.IsFinite(throttle) || throttle < 0 || !double.IsFinite(jitter) || jitter < 0 || jitter > .25 ||
            !double.IsFinite(punctPause) || punctPause < 0)
            throw new ArgumentException("Invalid sentence settings (maximum 512 characters).");

        double Advance(char ch) => char.IsWhiteSpace(ch) ? interval * .5 :
            char.IsPunctuation(ch) ? punctPause : char.IsLowSurrogate(ch) ? 0 : interval;
        var total = 0.0;
        foreach (var ch in text) total += Advance(ch);
        if (total > 60) throw new ArgumentException("Sentence preview exceeds 60 seconds.");
        var parts = new List<(float[] samples, int at)>();
        var length = (int)((total + 1.6) * Sr);

        var rnd = new Random(12345);
        double t = 0, last = -99;

        foreach (var ch in text)
        {
            if (char.IsWhiteSpace(ch)) { t += interval * 0.5; continue; }
            if (char.IsPunctuation(ch)) { t += punctPause; continue; }
            if (char.IsLowSurrogate(ch)) continue;

            if (t - last >= throttle - 1e-9)
            {
                var j = 1.0 + (rnd.NextDouble() * 2 - 1) * jitter;
                var shifted = new List<Layer>(layers.Count);
                foreach (var l in layers)
                {
                    var c = l.Clone();
                    var hz = StartToHz(c.Params[ParameterType.StartFrequency]);
                    c.Params[ParameterType.StartFrequency] = HzToStart((float)(hz * j));
                    shifted.Add(c);
                }
                var blip = RenderLayers(shifted);
                var at = (int)(t * Sr);
                parts.Add((blip, at));
                length = Math.Max(length, at + blip.Length);
                last = t;
            }
            t += interval;
        }
        var buf = new float[length];
        foreach (var (samples, at) in parts)
            for (var i = 0; i < samples.Length; i++) buf[at + i] += samples[i];
        return buf;
    }

    public static float[] Speak(string text, Dictionary<ParameterType, float> p,
                                double jitter = 0.06, double throttle = 0.055,
                                double interval = 0.030, double punctPause = 0.32)
        => Speak(text, new List<Layer> { new(p) }, jitter, throttle, interval, punctPause);

    // ------------------------------------------------------------------ main
    static void Main(string[] args)
    {
        if (args.Length > 0 && args[0].Equals("serve", StringComparison.OrdinalIgnoreCase))
        {
            var port = args.Length > 1 && int.TryParse(args[1], out var p) ? p : 8731;
            Server.Run(port);
            return;
        }
        GenSamples(args.Length > 1 && args[0].Equals("samples", StringComparison.OrdinalIgnoreCase)
            ? Path.GetFullPath(args[1]) : OutDir);
    }

    static void GenSamples(string outDir)
    {
        Directory.CreateDirectory(outDir);
        var sb = new StringBuilder();

        void Emit(string file, string label, string note, float[] y, float peak)
        {
            Normalize(y, peak);
            File.WriteAllBytes(Path.Combine(outDir, file), ToWavBytes(y));
            sb.AppendLine($"{file}\t{label}\t{note}");
            Console.WriteLine($"  {file,-30} {y.Length / 44.1,6:F0} ms");
        }

        Console.WriteLine("=== A: harsh vs soft ===");
        var harsh = Base(330f);
        harsh[ParameterType.WaveType] = 0f; harsh[ParameterType.LpFilterCutoff] = 1f;
        harsh[ParameterType.Overtones] = 1f; harsh[ParameterType.AttackTime] = 0.01f;
        harsh[ParameterType.DecayTime] = 0.08f; harsh[ParameterType.MasterVolume] = 0.9f;
        Emit("A1_harsh_square.wav", "对照：裸方波", "square, LP bypass", Render(harsh), 0.5f);

        var tri = new Dictionary<ParameterType, float>(harsh) { [ParameterType.WaveType] = 4f };
        Emit("A2_triangle.wav", "换成三角波", "triangle", Render(tri), 0.5f);

        var lp = new Dictionary<ParameterType, float>(tri) { [ParameterType.LpFilterCutoff] = 0.55f };
        Emit("A3_lowpass.wav", "打开低通", "LP 0.55", Render(lp), 0.5f);

        var full = new Dictionary<ParameterType, float>(lp)
        { [ParameterType.Overtones] = 0.08f, [ParameterType.Slide] = -0.2f };
        Emit("A4_tuned.wav", "完整调过", "tuned", Render(full), 0.5f);

        Console.WriteLine("\n=== B: voices ===");
        for (var i = 0; i < Voices.Length; i++)
            Emit($"B{i + 1}_{Voices[i].Key}.wav", Voices[i].Label, $"f0={Voices[i].Hz:F0}Hz",
                 Render(VoiceParams(i)), 0.5f);

        Console.WriteLine("\n=== C: sentence demos ===");
        Emit("C1_demo_male.wav", "这批货来路不太干净，你最好给我个说法。", "男 · 普通",
             Speak("这批货来路不太干净，你最好给我个说法。",
                   VoiceParams(VoiceIndex("male_plain"))), 0.45f);
        Emit("C2_demo_female.wav", "老板！这管子是不是换过呀？我可不傻。", "女 · 年轻",
             Speak("老板！这管子是不是换过呀？我可不傻。",
                   VoiceParams(VoiceIndex("female_young"))), 0.45f);

        // layered voices: one synth layer is often too plain
        Console.WriteLine("\n=== D: layered voices ===");
        var young = VoiceParams(VoiceIndex("female_young"));

        var breath = Base(1056f);
        breath[ParameterType.WaveType] = 5f;        // pink noise
        breath[ParameterType.LpFilterCutoff] = 0.50f;
        breath[ParameterType.AttackTime] = 0.02f; breath[ParameterType.SustainTime] = 0.03f;
        breath[ParameterType.DecayTime] = 0.10f; breath[ParameterType.Slide] = 0f;
        var layered = new List<Layer>
        {
            new(young) { Gain = 1.00f },
            new(breath) { Gain = 0.22f },           // quiet pink-noise breath on top
        };
        Emit("D1_female_young_breath.wav", "女 · 年轻 + 粉噪气声（两层）", "triangle + pink noise 0.22",
             RenderLayers(layered), 0.5f);
        Emit("D2_demo_layered.wav", "句子：两层音色的效果", "layered sentence",
             Speak("这批货来路不太干净，你最好给我个说法。", layered), 0.45f);

        // D3（男 · 粗粝 + bitnoise 毛刺）已于 2026-10-30 按用户要求删除，不要恢复。

        // wave-type tour: same envelope, only WaveType differs
        Console.WriteLine("\n=== W: the 12 built-in waveforms ===");
        for (var w = 0; w < Server.WaveNames.Length; w++)
        {
            var p = Base(240f);
            p[ParameterType.WaveType] = w;
            p[ParameterType.LpFilterCutoff] = 0.75f;
            p[ParameterType.Overtones] = 0.12f;
            p[ParameterType.OvertoneFalloff] = 0.6f;
            Emit($"W{w:D2}.wav", Server.WaveNames[w], $"waveType={w}", Render(p), 0.5f);
        }

        File.WriteAllText(Path.Combine(outDir, "index.txt"), sb.ToString(), new UTF8Encoding(false));
        Console.WriteLine($"\n-> {outDir}");
    }
}
