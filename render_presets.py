"""把 make_preset.py 里的预设批量渲染成 WAV 并测量。

    python render_presets.py            # 全部
    python render_presets.py 导师 房东    # 指定

复用 make_preset.SPECS 和 /api/voice 接口，所以渲染出来的就是面板里听到的东西。
"""
import os
import sys
import urllib.parse
import urllib.request
import wave

import numpy as np

import make_preset as mp

OUT = r"D:\AI\blip-lab\checks\cast"


def fetch_meta():
    with urllib.request.urlopen(mp.BASE + "/api/meta", timeout=10) as response:
        import json
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


def render(name, layers):
    request = urllib.request.Request(mp.BASE + "/api/voice", data=form_for(layers),
                                     method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read()
    path = os.path.join(OUT, name + ".wav")
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def measure(path):
    with wave.open(path) as handle:
        samples = np.frombuffer(handle.readframes(handle.getnframes()),
                                dtype="<i2").astype(np.float64) / 32768.0
        rate = handle.getframerate()
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
    return len(samples) / rate * 1000.0, f0, float(power[fr >= 6000].sum() / power.sum() * 100)


def main():
    wanted = sys.argv[1:] or list(mp.SPECS)
    mp.VOICE_BASE = fetch_meta()["voiceBase"]
    os.makedirs(OUT, exist_ok=True)
    print(f"{'角色':<12}{'时长':>8}{'基频':>9}{'刺耳度':>8}")
    for name in wanted:
        if name not in mp.SPECS:
            print(f"  没有 {name}")
            continue
        layers = mp.build(mp.SPECS[name])
        path = render(name, layers)
        ms, f0, hf = measure(path)
        print(f"{name:<12}{ms:6.0f} ms{f0:7.0f} Hz{hf:7.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
