using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Wikman.Synthesizer.Sfxr;

internal static class Checks
{
    static int failures;
    static void Check(string name, Action test)
    {
        try { test(); Console.WriteLine("PASS " + name); }
        catch (Exception e) { failures++; Console.WriteLine("FAIL " + name + ": " + e.Message); }
    }
    static void Assert(bool value, string message)
    {
        if (!value) throw new Exception(message);
    }
    static int Main()
    {
        Check("frequency lower bound", () =>
            Assert(float.IsFinite(Program.HzToStart(0)), "0 Hz produces NaN"));
        Check("frequency upper bound", () =>
            Assert(Program.HzToStart(9000) <= 1, "outside synth range"));
        Check("spaces use half a character interval", () =>
        {
            var y = Program.Speak("a" + new string(' ', 100) + "b", Program.VoiceParams(Program.VoiceIndex("female_young")), jitter: 0);
            var last = Array.FindLastIndex(y, x => Math.Abs(x) > 1e-5);
            Assert(last < 2 * 44100, "spaces add punctuation-sized pauses");
            Assert(last > 1.5 * 44100, "spaces clipped the final sound");
        });
        Check("quotes and brackets are silent", () =>
        {
            var y = Program.Speak("\"（）【】「」‘’", Program.VoiceParams(Program.VoiceIndex("female_young")));
            Assert(y.All(x => x == 0), "punctuation generates blips");
        });
        Check("long blip tail is retained", () =>
        {
            var p = Program.VoiceParams(Program.VoiceIndex("female_young"));
            p[ParameterType.DecayTime] = 1;
            var single = Program.Render(p);
            var sentence = Program.Speak("a", p, jitter: 0);
            Assert(sentence.Length >= single.Length, "tail truncated");
            Assert(single.SequenceEqual(sentence.Take(single.Length)), "tail differs");
        });
        Check("delayed layer is retained", () =>
        {
            var layers = new List<Program.Layer> { new(Program.VoiceParams(Program.VoiceIndex("female_young"))) { DelayMs = 2000 } };
            var single = Program.RenderLayers(layers);
            var sentence = Program.Speak("a", layers, jitter: 0);
            Assert(sentence.Length >= single.Length, "delayed sound truncated");
            Assert(sentence.Any(x => x != 0), "delayed sound lost");
        });
        Check("parallel rendering stays isolated", () =>
        {
            var expected = Enumerable.Range(0, Program.VoiceCount).Select(i => Program.Render(Program.VoiceParams(i))).ToArray();
            Parallel.For(0, 96, i =>
            {
                var index = i % Program.VoiceCount;
                var actual = Program.Render(Program.VoiceParams(index));
                Assert(actual.SequenceEqual(expected[index]), "render state crossed requests");
            });
        });
        var watch = System.Diagnostics.Stopwatch.StartNew();
        var bytes = GC.GetAllocatedBytesForCurrentThread();
        for (var i = 0; i < 48; i++) Program.Render(Program.VoiceParams(i % Program.VoiceCount));
        Console.WriteLine($"Host benchmark: 48 blips in {watch.Elapsed.TotalMilliseconds:F1} ms, " +
            $"thread allocations {(GC.GetAllocatedBytesForCurrentThread() - bytes) / 1024.0:F0} KiB (not Unity performance).");
        Console.WriteLine($"{7 - failures}/7 checks passed");
        return failures == 0 ? 0 : 1;
    }
}
