"""Regression check for the generated blips.

    python verify.py        exit 0 = all good, exit 1 = something drifted

This is the only runnable check behind the synth work. It catches the two
mistakes that actually happened while building it:

  * pitch off by a factor -- the 8x super-sample bug (startFreq -> Hz mapping)
  * the engine degrading into a clipped square with no envelope, which shows up
    as a huge share of energy above 6 kHz

Pitch is taken as the strongest spectral peak after DC removal, in 60..3000 Hz.
An earlier harmonic-product-spectrum attempt reported octave-low values on
zero-padded short clips, so it is not used here.

Voices deliberately glide downward (Slider < 0), so the measured fundamental is
a little below the start frequency; the tolerance allows for that.
"""
import os
import argparse
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "bfxr-samples")

# file -> (start frequency Hz, min ms, max ms, max % of energy above 6 kHz)
EXPECTED = [
    ("B1_male_plain.wav",    145, 40, 220, 4.0),
    ("B2_male_old.wav",      122, 60, 280, 4.0),
    ("B3_female_young.wav", 1056, 40, 220, 4.0),
    ("B4_female_mature.wav", 620, 40, 220, 4.0),
    ("B5_neutral.wav",       420, 40, 220, 4.0),
]

TOLERANCE_PCT = 15.0


def load(path):
    with wave.open(path, "rb") as w:
        raw = w.readframes(w.getnframes())
        sr = w.getframerate()
    return np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0, sr


def remove_dc(y, sr):
    """High-pass by subtracting a short moving average -- kills the envelope
    pedestal that otherwise wins the 'strongest peak' contest."""
    win = max(3, int(sr / 50))          # ~50 Hz corner
    kernel = np.ones(win) / win
    return y - np.convolve(y, kernel, mode="same")


def f0_peak(y, sr, fmin=60.0, fmax=3000.0):
    y = remove_dc(y, sr)
    n = 1 << max(12, int(np.ceil(np.log2(max(len(y), 2)))))
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)), n))
    freqs = np.fft.rfftfreq(n, 1.0 / sr)

    lo = np.searchsorted(freqs, fmin)
    hi = np.searchsorted(freqs, fmax)
    if hi - lo < 3:
        return 0.0

    band = spec[lo:hi]
    k = int(np.argmax(band)) + lo
    if k <= 0 or k >= len(spec) - 1:
        return float(freqs[k])

    # parabolic interpolation on log magnitude for sub-bin accuracy
    a, b, c = np.log(spec[k - 1] + 1e-12), np.log(spec[k] + 1e-12), np.log(spec[k + 1] + 1e-12)
    denom = a - 2 * b + c
    shift = 0.5 * (a - c) / denom if abs(denom) > 1e-12 else 0.0
    return float(freqs[k] + shift * (freqs[1] - freqs[0]))


def hf_share(y, sr):
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)), 1 << 15))
    freqs = np.fft.rfftfreq(1 << 15, 1.0 / sr)
    power = spec ** 2
    return float(power[freqs >= 6000].sum() / (power.sum() + 1e-12) * 100.0)


def main():
    global SAMPLES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", default=SAMPLES, help="Directory of freshly generated WAVs")
    SAMPLES = parser.parse_args().samples
    if not os.path.isdir(SAMPLES):
        print(f"missing {SAMPLES}; run: dotnet run --project bfxr-host")
        return 1

    failures = []
    print(f"{'file':24s} {'ms':>6s} {'f0':>7s} {'start':>7s} {'dev':>7s} {'>6k':>6s}  verdict")
    print("-" * 76)

    for name, exp_f0, ms_lo, ms_hi, hf_max in EXPECTED:
        path = os.path.join(SAMPLES, name)
        if not os.path.exists(path):
            print(f"{name:24s}  MISSING")
            failures.append(f"{name}: file missing")
            continue

        y, sr = load(path)
        peak = float(np.max(np.abs(y))) if len(y) else 0.0
        if len(y) < 256 or peak < 1e-4:
            print(f"{name:24s}  SILENT")
            failures.append(f"{name}: silent or too short")
            continue

        ms = len(y) / sr * 1000.0
        f0 = f0_peak(y, sr)
        dev = (f0 / exp_f0 - 1.0) * 100.0
        hf = hf_share(y, sr)

        problems = []
        if abs(dev) > TOLERANCE_PCT:
            problems.append(f"pitch {dev:+.0f}%")
        if not (ms_lo <= ms <= ms_hi):
            problems.append(f"length {ms:.0f}ms (want {ms_lo}-{ms_hi})")
        if hf > hf_max:
            problems.append(f"harshness {hf:.1f}% > {hf_max}%")
        if peak < 0.3:
            problems.append(f"peak {peak:.2f} low")

        print(f"{name:24s} {ms:6.0f} {f0:7.0f} {exp_f0:7.0f} {dev:+6.1f}% {hf:5.1f}%  "
              f"{'OK' if not problems else ' / '.join(problems)}")
        if problems:
            failures.append(f"{name}: {' / '.join(problems)}")

    print()
    if failures:
        print(f"FAIL - {len(failures)} problem(s):")
        for f in failures:
            print("   -", f)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
