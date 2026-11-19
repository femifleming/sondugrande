"""Shared pieces of the Songrande tests: test sounds and project states."""
import os
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from songrande import render, space, wavio            # noqa: E402
from songrande.scene import Scene                     # noqa: E402

TMP = tempfile.mkdtemp(prefix="songrande_tests_")


def noiseSound(name="noise.wav", seconds=3.0, rate=44100, channels=1):
    """Band-limited noise: audible at every place in the file."""
    path = os.path.join(TMP, name)
    if not os.path.isfile(path):
        rng = np.random.default_rng(3)
        n = int(seconds * rate)
        out = []
        for c in range(channels):
            spec = np.fft.rfft(rng.standard_normal(n))
            freqs = np.fft.rfftfreq(n, 1.0 / rate)
            spec[(freqs < 150) | (freqs > 6000)] = 0
            x = np.fft.irfft(spec, n)
            out.append(x / np.abs(x).max() * 0.8)
        wavio.write(path, np.array(out), rate)
    return path


def sineSound(name="sine.wav", freq=1000.0, seconds=3.0, rate=44100):
    path = os.path.join(TMP, name)
    if not os.path.isfile(path):
        t = np.arange(int(seconds * rate)) / float(rate)
        wavio.write(path, 0.8 * np.sin(2 * np.pi * freq * t), rate)
    return path


def roomPoints(points):
    """Room points (right, front, up in radii) as canvas points."""
    return [tuple(float(v) for v in space.room_to_canvas(np.asarray(p, dtype=float))) for p in points]


def stateWith(build, sound=None, **spaceValues):
    """A project state whose scene is made by build(scene)."""
    state = render.emptyState()
    scene = Scene()
    build(scene)
    state.update(scene.getState())
    state["ControlPanel"]["sound"] = sound or noiseSound()
    state["Space"].update(spaceValues)
    return state


def still(room_point):
    """A build function: one stream standing at a point of the room."""
    def build(scene):
        p = roomPoints([room_point])[0]
        scene.addTrajectory('line', points=[p, (p[0] + 1e-3, p[1], p[2])])
    return build


def renderState(state, name="out.wav", dur=2.0, **overrides):
    out = os.path.join(TMP, name)
    path, channels = render.render(state, out, dur=dur, overrides=overrides or None)
    samples, rate = wavio.read(path)
    return samples, rate
