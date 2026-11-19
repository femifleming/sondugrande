"""Makes the example project: examples/demo.sgr and its sound examples/demo.wav.

    python examples/make_demo.py

The sound is synthesised here (bell-like tones over a slow noise swell), so
nothing in this folder is anybody else's recording.
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from sondugrande import render, space, wavio          # noqa: E402
from sondugrande.scene import Scene                   # noqa: E402


def makeSound(path, seconds=8.0, rate=44100):
    rng = np.random.default_rng(11)
    n = int(seconds * rate)
    t = np.arange(n) / rate
    out = np.zeros(n)
    # bells: two-operator FM with a decaying index, on a just pentatonic scale
    scale = [1, 9 / 8, 5 / 4, 3 / 2, 5 / 3, 2, 9 / 4, 5 / 2, 3]
    when = 0.05
    while when < seconds - 0.6:
        f = 174.61 * rng.choice(scale) * rng.choice([0.5, 1, 1, 2])
        dur = rng.uniform(0.6, 1.8)
        m = int(dur * rate)
        start = int(when * rate)
        m = min(m, n - start)
        tt = np.arange(m) / rate
        env = np.exp(-tt * rng.uniform(2.5, 5.0)) * np.minimum(1.0, tt / 0.004)
        index = 3.0 * np.exp(-tt * 6.0)
        out[start:start + m] += rng.uniform(0.25, 0.6) * env * np.sin(
            2 * np.pi * f * tt + index * np.sin(2 * np.pi * f * 2.76 * tt))
        when += rng.uniform(0.12, 0.5)
    # a breath of noise underneath that opens and closes
    spec = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    spec *= np.exp(-((np.log2(np.maximum(freqs, 1.0) / 900.0)) ** 2) / 1.2)
    noise = np.fft.irfft(spec, n)
    noise *= 0.5 + 0.5 * np.sin(2 * np.pi * 0.23 * t - 1.0)
    out += 0.25 * noise / np.abs(noise).max()
    fade = int(0.02 * rate)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    out *= 0.85 / np.abs(out).max()
    wavio.write(path, out, rate, bits=16)


def room(points):
    return [tuple(float(v) for v in space.room_to_canvas(np.asarray(p, dtype=float))) for p in points]


def makeProject(path, sound):
    state = render.emptyState()
    scene = Scene()
    # 1. once round the listener at ear level, a little slower at the back
    a = np.linspace(0, 2 * np.pi, 420, endpoint=False)
    ring = np.stack([-np.sin(a) * 0.82, np.cos(a) * 0.82, np.zeros_like(a)], axis=1)
    t1 = scene.addTrajectory('free', points=room(ring), closed=False)
    # 2. a spiral climbing from under the floor to overhead, on the right
    scene.setOscilPeriod(3)
    scene.setOscilScaling(1.6)
    t2 = scene.addTrajectory('spiral', center=room([(0.42, 0.25, 0.1)])[0], radius=0.28 * space.HALF)
    t2.setDirection(2)
    # 3. a circle on the loudspeaker sphere, high up at the front left
    centre = np.array([-0.45, 0.55, 0.70])
    centre = centre / np.linalg.norm(centre)
    u = np.cross([0, 0, 1.0], centre)
    u /= np.linalg.norm(u)
    v = np.cross(centre, u)
    cv = lambda r: (float(r[0]), -float(r[1]), float(r[2]))
    t3 = scene.addTrajectory('circle', center=room([centre])[0], radius=0.33 * space.HALF,
                             basis=(cv(u), cv(v), cv(centre)), sphere=1.0)
    t3.setTimeSpeed(40)
    # 4. a line through the room from behind left, low, to the front right, high
    line = np.stack([np.linspace(-0.85, 0.8, 200), np.linspace(-0.8, 0.85, 200), np.linspace(-0.25, 0.6, 200)], axis=1)
    t4 = scene.addTrajectory('line', points=room(line))
    t4.setDirection(2)
    t4.setStep(2)
    # a delay ball the ring passes through at the back, and a reverb ball up in the spiral
    back = scene.addFxBall(1, center=room([(0.0, -0.82, 0.0)])[0], size=0.55 * space.HALF)
    back.sliders.update({"slider1": 0.33, "slider2": 0.55, "slider3": 1.0, "slider4": 0.2})
    up = scene.addFxBall(0, center=room([(0.42, 0.25, 0.55)])[0], size=0.5 * space.HALF)
    up.sliders.update({"slider1": 0.85, "slider2": 6000, "slider3": 0.8, "slider4": 0.6})
    state.update(scene.getState())
    state["ControlPanel"]["sound"] = os.path.basename(sound)
    state["ControlPanel"]["globalamp"] = 0.7
    state["ControlFrame"].update({"density": 28, "graindur": 260, "rndpos": 0.02, "rnddur": 0.2})
    state["Space"].update({"scatter": 10.0, "reverb": 0.18, "reverbTime": 0.55, "roomSize": 6.0})
    state["View"] = {"view": "3D", "yaw": math.radians(-28.0), "pitch": math.radians(30.0), "zoom": 1.0,
                     "drawOn": 0, "penHeight": 0.0, "sphereRadius": 1.0}
    render.saveProject(state, path)


if __name__ == "__main__":
    sound = os.path.join(HERE, "demo.wav")
    makeSound(sound)
    makeProject(os.path.join(HERE, "demo.sgr"), sound)
    print("examples/demo.wav, examples/demo.sgr")
