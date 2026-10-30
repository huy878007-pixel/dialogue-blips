"""从 /api/state 里的实际预设渲染并测量，反映"面板里现在是什么"。

和 render_presets.py 的区别：那个读 make_preset.SPECS（我的种子），
这个读共享状态（含用户手动调过的版本）。
"""
import json
import os
import urllib.parse
import urllib.request
import wave

import numpy as np

BASE = "http://127.0.0.1:8731"
OUT = r"D:\AI\blip-lab\checks\cast-state"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as response:
        return json.loads(response.read())


def form_for(layers):
    fields = []
    for i, layer in enumerate(layers):
        fields.append((f"layer{i}.hz", layer["hz"]))
        fields.append((f"layer{i}.gain", layer["gain"]))
        fields.append((f"layer{i}.delay", layer["delay"]))
        fields.append((f"layer{i}.mute", 1 if layer["mute"] else 0))
        for key, value in layer["p"].items():
            fields.append((f"layer{i}.{key}", value))
    return urllib.parse.urlencode(fields).encode()


def measure(samples, rate):
    size = max(3, int(rate / 50))
    centred = samples - np.convolve(samples, np.ones(size) / size, mode="same")
    n = 1 << max(12, int(np.ceil(np.log2(max(len(samples), 2)))))
    spectrum = np.abs(np.fft.rfft(centred * np.hanning(len(samples)), n))
    freqs = np.fft.rfftfreq(n, 1 / rate)
    lo, hi = np.searchsorted(freqs, 60), np.searchsorted(freqs, 3500)
    f0 = freqs[lo + int(np.argmax(spectrum[lo:hi]))]
    full = np.abs(np.fft.rfft(samples * np.hanning(len(samples)), 1 << 15))
    fr = np.fft.rfftfreq(1 << 15, 1 / rate)
    power = full ** 2
    hf = float(power[fr >= 6000].sum() / power.sum() * 100)
    return len(samples) / rate * 1000.0, f0, hf


def main():
    state = get("/api/state")["state"]
    presets = state.get("presets") or {}
    os.makedirs(OUT, exist_ok=True)

    rows = []
    for name, layers in presets.items():
        request = urllib.request.Request(BASE + "/api/voice", data=form_for(layers),
                                         method="POST")
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read()
        path = os.path.join(OUT, name.replace("/", "_") + ".wav")
        with open(path, "wb") as handle:
            handle.write(data)
        with wave.open(path) as handle:
            samples = np.frombuffer(handle.readframes(handle.getnframes()),
                                    dtype="<i2").astype(np.float64) / 32768.0
            rate = handle.getframerate()
        ms, f0, hf = measure(samples, rate)
        rows.append((f0, name, ms, len(layers), hf))

    rows.sort()
    print(f"{'Hz':>6}  {'角色':<14}{'时长':>7}{'层':>3}{'刺耳':>7}")
    for f0, name, ms, depth, hf in rows:
        print(f"{f0:6.0f}  {name:<14}{ms:6.0f} ms{depth:3d}{hf:6.2f}%")
    print(f"\n共 {len(rows)} 个预设")


if __name__ == "__main__":
    main()
