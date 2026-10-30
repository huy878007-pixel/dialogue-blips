// Tiny local HTTP server so the browser console can drive the real bfxr engine.
// TcpListener instead of HttpListener: no URL ACL / admin reservation needed.
//
// GET  /                        -> panel.html
// GET  /api/synth?<params>      -> one-layer WAV
// POST /api/voice               -> layered WAV   (body: layer0.WaveType=4&layer0.hz=330&layer0.gain=1&...)
// POST /api/sentence            -> layered sentence preview (adds text/jitter/throttle/interval)
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Text.Json;
using Wikman.Synthesizer.Sfxr;

internal static class Server
{
    static readonly Lazy<ConsoleState> SharedState = new(() => new ConsoleState());
    sealed class HttpError : Exception
    {
        public readonly int Status;
        public HttpError(int status, string message) : base(message) { Status = status; }
    }
    public static readonly string[] WaveNames =
    {
        "方波 Square", "锯齿 Saw", "正弦 Sine", "白噪音 Noise",
        "三角 Triangle", "粉噪音 Pink Noise", "Tan 失真", "哨音 Whistle",
        "Breaker 碎波", "Bitnoise 1-bit", "Combo 轮换", "Buzz 蜂鸣",
    };

    public static void Run(int port)
    {
        var listener = new TcpListener(IPAddress.Loopback, port);
        listener.Start();
        Console.WriteLine($"console -> http://127.0.0.1:{port}/");
        Console.WriteLine("Ctrl+C 结束");
        while (true)
        {
            var client = listener.AcceptTcpClient();
            ThreadPool.QueueUserWorkItem(_ => Handle(client));
        }
    }

    static void Handle(TcpClient client)
    {
        using var ownedClient = client;
        using var stream = client.GetStream();
        client.ReceiveTimeout = 3000;
        client.SendTimeout = 3000;
        try
        {
            var req = ReadRequest(stream);
            if (req == null) return;
            var (verb, path, query, body) = req.Value;
            if (path == "/api/state")
            {
                if (verb == "GET")
                    Respond(stream, "application/json; charset=utf-8", Encoding.UTF8.GetBytes(SharedState.Value.Read()));
                else if (verb == "PUT" || verb == "PATCH")
                {
                    var result = SharedState.Value.Update(body, verb == "PATCH");
                    Respond(stream, "application/json; charset=utf-8", Encoding.UTF8.GetBytes(result.json), result.status);
                }
                else throw new HttpError(405, "Method Not Allowed");
                return;
            }
            var method = path == "/api/voice" || path == "/api/sentence" ? "POST" : "GET";
            if (verb != method) throw new HttpError(405, "Method Not Allowed");

            switch (path)
            {
                case "/":
                case "/index.html":
                {
                    var file = Path.Combine(AppContext.BaseDirectory, "panel.html");
                    Respond(stream, "text/html; charset=utf-8", File.ReadAllBytes(file));
                    break;
                }
                case "/api/synth":
                {
                    var p = ParseParams(query, "");
                    var y = Program.Render(p);
                    Program.LimitPeak(y, 0.95f);
                    Respond(stream, "audio/wav", Program.ToWavBytes(y));
                    break;
                }
                case "/api/voice":
                {
                    var layers = ParseLayers(body.Length > 0 ? body : query);
                    if (layers.Count == 0) layers.Add(new Program.Layer(Program.DefaultParams()));
                    var y = Program.RenderLayers(layers);
                    Program.LimitPeak(y, 0.95f);
                    Respond(stream, "audio/wav", Program.ToWavBytes(y));
                    break;
                }
                case "/api/sentence":
                {
                    var src = body.Length > 0 ? body : query;
                    var layers = ParseLayers(src);
                    if (layers.Count == 0) layers.Add(new Program.Layer(Program.DefaultParams()));
                    var text = Field(src, "text") ?? "这批货来路不太干净，你最好给我个说法。";
                    var jitter = Bounded(Field(src, "jitter"), 6f, 0, 25) / 100.0;
                    var throttle = Bounded(Field(src, "throttle"), 55f, 20, 200) / 1000.0;
                    var interval = Bounded(Field(src, "interval"), 30f, 10, 90) / 1000.0;
                    var y = Program.Speak(text, layers, jitter, throttle, interval);
                    Program.LimitPeak(y, 0.95f);
                    Respond(stream, "audio/wav", Program.ToWavBytes(y));
                    break;
                }
                case "/api/meta":
                {
                    Respond(stream, "application/json; charset=utf-8", Encoding.UTF8.GetBytes(MetaJson()));
                    break;
                }
                default:
                    Respond(stream, "text/plain; charset=utf-8", Encoding.UTF8.GetBytes("404 " + path), 404);
                    break;
            }
        }
        catch (Exception e)
        {
            Console.Error.WriteLine($"[server] {e.GetType().Name}: {e.Message}");
            var status = e is HttpError h ? h.Status : e is ArgumentException || e is JsonException ? 400 : e is IOException ? 408 : 500;
            try { Respond(stream, "text/plain; charset=utf-8", Encoding.UTF8.GetBytes(status == 500 ? "Internal Server Error" : e.Message), status); }
            catch (IOException) { } // The peer may already have disconnected.
            catch (SocketException) { }
        }
    }

    // ------------------------------------------------------------ http plumbing
    static void Respond(Stream s, string contentType, byte[] body, int status = 200)
    {
        var head = Encoding.ASCII.GetBytes(
            $"HTTP/1.1 {status} {(status == 200 ? "OK" : "Error")}\r\n" +
            $"Content-Type: {contentType}\r\n" +
            $"Content-Length: {body.Length}\r\n" +
            "Cache-Control: no-store\r\n" +
            "Connection: close\r\n\r\n");
        s.Write(head, 0, head.Length);
        s.Write(body, 0, body.Length);
        s.Flush();
    }

    static (string verb, string path, string query, string body)? ReadRequest(NetworkStream stream)
    {
        // Fixed limits and one deadline cover incomplete headers and incomplete bodies.
        var deadline = System.Diagnostics.Stopwatch.StartNew();
        int Read(byte[] bytes, int offset, int count)
        {
            var remaining = 3000 - (int)deadline.ElapsedMilliseconds;
            if (remaining <= 0) throw new HttpError(408, "Request Timeout");
            stream.ReadTimeout = remaining;
            return stream.Read(bytes, offset, count);
        }
        var header = new byte[8192];
        var count = 0;
        while (true)
        {
            if (count == header.Length) throw new HttpError(413, "Headers too large");
            if (Read(header, count, 1) == 0) throw new HttpError(400, "Incomplete headers");
            count++;
            if (count >= 4 && header[count - 4] == 13 && header[count - 3] == 10 &&
                header[count - 2] == 13 && header[count - 1] == 10) break;
        }
        var head = Encoding.ASCII.GetString(header, 0, count - 4);
        var lines = head.Split(new[] { "\r\n" }, StringSplitOptions.None);
        var parts = lines[0].Split(' ');
        if (parts.Length != 3) throw new HttpError(400, "Invalid request line");

        var contentLength = 0;
        for (var i = 1; i < lines.Length; i++)
        {
            var c = lines[i].IndexOf(':');
            if (c > 0 && lines[i][..c].Trim().Equals("Transfer-Encoding", StringComparison.OrdinalIgnoreCase))
                throw new HttpError(400, "Transfer-Encoding is unsupported");
            if (c > 0 && lines[i][..c].Trim().Equals("Content-Length", StringComparison.OrdinalIgnoreCase))
            {
                if (!int.TryParse(lines[i][(c + 1)..].Trim(), out contentLength) || contentLength < 0)
                    throw new HttpError(400, "Invalid Content-Length");
                var limit = parts[1].Split('?')[0] == "/api/state" ? 2 * 1024 * 1024 : 65536;
                if (contentLength > limit) throw new HttpError(413, "Body too large");
            }
        }

        var bodyBytes = new byte[contentLength];
        var received = 0;
        while (received < contentLength)
        {
            var read = Read(bodyBytes, received, contentLength - received);
            if (read == 0) throw new HttpError(400, "Incomplete body");
            received += read;
        }
        var body = Encoding.UTF8.GetString(bodyBytes);

        var target = parts[1];
        var q = target.IndexOf('?');
        var path = q >= 0 ? target[..q] : target;
        var query = q >= 0 ? target[(q + 1)..] : "";
        return (parts[0], path, query, body);
    }

    static Dictionary<string, string> ParseQuery(string query)
    {
        var d = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (string.IsNullOrEmpty(query)) return d;
        foreach (var pair in query.Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            var eq = pair.IndexOf('=');
            if (eq < 0) continue;
            d[WebUtility.UrlDecode(pair[..eq])] = WebUtility.UrlDecode(pair[(eq + 1)..]);
        }
        return d;
    }

    static string Field(string query, string key)
        => ParseQuery(query).TryGetValue(key, out var v) ? v : null;

    static float Bounded(string s, float fallback, float min, float max)
    {
        if (s == null) return fallback;
        if (!float.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var f) ||
            !float.IsFinite(f) || f < min || f > max)
            throw new ArgumentException($"Expected a finite value in [{min}, {max}].");
        return f;
    }

    static float Parameter(ParameterType pt, string value)
    {
        var db = new ParameterDatabase();
        var f = Bounded(value, db.GetDefault(pt), db.GetMin(pt),
            pt == ParameterType.WaveType ? WaveNames.Length - 1 : db.GetMax(pt));
        if (pt == ParameterType.WaveType && f != MathF.Truncate(f))
            throw new ArgumentException("WaveType must be an integer.");
        return f;
    }

    static Dictionary<ParameterType, float> ParseParams(string query, string prefix)
    {
        var p = Program.DefaultParams();
        foreach (var kv in ParseQuery(query))
        {
            if (!kv.Key.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) continue;
            var name = kv.Key[prefix.Length..];
            if (Enum.TryParse<ParameterType>(name, true, out var pt) && pt != ParameterType.None && Enum.IsDefined(pt))
                p[pt] = Parameter(pt, kv.Value);
        }
        return p;
    }

    /// <summary>Body keys look like: layer0.WaveType=4, layer0.hz=330, layer0.gain=1,
    /// layer0.delay=0, layer0.mute=0, then layer1.* ...</summary>
    static List<Program.Layer> ParseLayers(string form)
    {
        var fields = ParseQuery(form);
        var indexes = new SortedSet<int>();
        foreach (var k in fields.Keys)
        {
            if (!k.StartsWith("layer", StringComparison.OrdinalIgnoreCase)) continue;
            var dot = k.IndexOf('.');
            if (dot < 0) continue;
            if (dot <= 5 || !int.TryParse(k[5..dot], out var idx) || idx < 0 || idx >= 8)
                throw new ArgumentException("Layer index must be in [0, 7].");
            indexes.Add(idx);
        }

        var layers = new List<Program.Layer>();
        foreach (var i in indexes)
        {
            var prefix = $"layer{i}.";
            var p = Program.DefaultParams();
            foreach (var kv in fields)
            {
                if (!kv.Key.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) continue;
                var name = kv.Key[prefix.Length..];
                if (name.Equals("hz", StringComparison.OrdinalIgnoreCase))
                    p[ParameterType.StartFrequency] = Program.HzToStart(Bounded(kv.Value, 200f, 3.528f, 3531.528f));
                else if (Enum.TryParse<ParameterType>(name, true, out var pt) && pt != ParameterType.None && Enum.IsDefined(pt))
                    p[pt] = Parameter(pt, kv.Value);
            }
            // Explicit Hz takes precedence regardless of the form field order.
            if (fields.TryGetValue(prefix + "hz", out var hz))
                p[ParameterType.StartFrequency] = Program.HzToStart(Bounded(hz, 200f, 3.528f, 3531.528f));
            layers.Add(new Program.Layer(p)
            {
                Gain = Bounded(fields.GetValueOrDefault($"{prefix}gain"), 1f, 0, 1.5f),
                DelayMs = Bounded(fields.GetValueOrDefault($"{prefix}delay"), 0f, 0, 120),
                Mute = Bounded(fields.GetValueOrDefault($"{prefix}mute"), 0f, 0, 1) > 0.5f,
            });
        }
        return layers;
    }

    static string MetaJson()
    {
        var db = new ParameterDatabase();
        var sb = new StringBuilder();
        sb.Append("{\"waves\":[");
        for (var i = 0; i < WaveNames.Length; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append($"\"{WaveNames[i]}\"");
        }
        sb.Append("],\"params\":[");
        var first = true;
        foreach (ParameterType pt in Enum.GetValues(typeof(ParameterType)))
        {
            if (pt == ParameterType.None) continue;
            if (!first) sb.Append(',');
            first = false;
            sb.Append($"{{\"key\":\"{pt}\",\"def\":{F(db.GetDefault(pt))},\"min\":{F(db.GetMin(pt))},\"max\":{F(pt == ParameterType.WaveType ? WaveNames.Length - 1 : db.GetMax(pt))}}}");
        }
        sb.Append("],");
        sb.Append(Program.PresetsJson()[1..]);
        return sb.ToString();
    }

    static string F(float v) => v.ToString("0.####", CultureInfo.InvariantCulture);
}
