"""
Songrande - reading WAV files of any channel count into numpy (for the tests
and the self-test's analysis; the application itself reads sound through pyo).

This file is part of Songrande, a derivative of SoundGrain (Olivier Belanger),
released under the GNU General Public License version 3 or later.
"""
import struct

import numpy as np


def read(path):
    """Returns (samples, rate): samples is a float array (channels, frames)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Not a WAV file: %s" % path)
    pos = 12
    fmt = None
    samples = None
    while pos + 8 <= len(data):
        tag = data[pos:pos + 4]
        size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if tag == b"fmt ":
            code, channels, rate, _, _, bits = struct.unpack("<HHIIHH", body[:16])
            if code == 0xFFFE and len(body) >= 26:
                code = struct.unpack("<H", body[24:26])[0]
            fmt = (code, channels, rate, bits)
        elif tag == b"data":
            samples = body
        pos += 8 + size + (size & 1)
    if fmt is None or samples is None:
        raise ValueError("Incomplete WAV file: %s" % path)
    code, channels, rate, bits = fmt
    if code == 3:
        flat = np.frombuffer(samples, dtype="<f4" if bits == 32 else "<f8").astype(float)
    elif bits == 16:
        flat = np.frombuffer(samples, dtype="<i2").astype(float) / 32768.0
    elif bits == 32:
        flat = np.frombuffer(samples, dtype="<i4").astype(float) / 2147483648.0
    elif bits == 24:
        raw = np.frombuffer(samples[:len(samples) // 3 * 3], dtype=np.uint8).reshape(-1, 3)
        ints = raw[:, 0].astype(np.int32) | (raw[:, 1].astype(np.int32) << 8) | (raw[:, 2].astype(np.int32) << 16)
        ints = np.where(ints >= 1 << 23, ints - (1 << 24), ints)
        flat = ints.astype(float) / 8388608.0
    else:
        raise ValueError("Unsupported WAV sample format in %s" % path)
    frames = len(flat) // channels
    return flat[:frames * channels].reshape(frames, channels).T.copy(), rate


def write(path, samples, rate=44100, bits=32):
    """Write a float array (channels, frames) or (frames,) as a WAV file:
    32-bit float, or 16-bit integers with bits=16."""
    a = np.asarray(samples, dtype=float)
    if a.ndim == 1:
        a = a[None, :]
    channels, frames = a.shape
    if bits == 16:
        body = np.round(np.clip(a.T, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
        fmt = struct.pack("<HHIIHH", 1, channels, int(rate), int(rate) * channels * 2, channels * 2, 16)
    else:
        body = a.T.astype("<f4").tobytes()
        fmt = struct.pack("<HHIIHH", 3, channels, int(rate), int(rate) * channels * 4, channels * 4, 32)
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(body)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
        f.write(b"data" + struct.pack("<I", len(body)) + body)
