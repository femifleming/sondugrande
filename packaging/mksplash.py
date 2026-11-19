# Songrande's splash picture, after SoundGrain's: the same round window, the
# waveform now a floor seen in perspective and the red trajectory leaving it.
#
#   python3 packaging/mksplash.py        (needs Pillow and numpy)
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from songrande import space        # noqa: E402

K = 4            # draw big, scale down
SIZE = 400
RED = (255, 0, 0)
GREY = (63, 63, 68)


def main():
    W = SIZE * K
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, W - 1, W - 1], fill=(0, 0, 0, 255))
    camera = space.Camera()
    camera.setSize(W, W)
    camera.yaw = math.radians(-24)
    camera.pitch = math.radians(33)
    camera.zoom = 1.55

    def line(points, colour, width):
        xy, depth = camera.project(np.asarray(points, dtype=float))
        xy = xy + np.array([0.0, 0.03 * W])
        d.line([tuple(p) for p in xy], fill=colour, width=width, joint="curve")

    # the sound on the floor: a waveform like SoundGrain's
    rng = np.random.default_rng(4)
    n = 900
    x = np.linspace(-1, 1, n)
    envelope = (0.25 + 0.75 * np.exp(-((x + 0.1) / 0.45) ** 2)) * (0.6 + 0.4 * np.sin(x * 7.0) ** 2)
    amp = envelope * rng.uniform(0.55, 1.0, n) * 0.62
    for i in range(n):
        line([(x[i], -amp[i], 0), (x[i], amp[i], 0)], GREY, K)
    # the edge of the floor and the loudspeaker circle
    line([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0), (-1, -1, 0)], (110, 110, 110), K)
    a = np.linspace(0, 2 * np.pi, 200)
    line(np.stack([np.cos(a), np.sin(a), np.zeros_like(a)], axis=1), (90, 90, 90), K)
    # a trajectory on the floor that climbs into a spiral
    t = np.linspace(0, 1, 700)
    turns = 2.6
    radius = 0.78 - 0.5 * t ** 1.5
    height = 0.95 * np.maximum(0.0, t - 0.25) ** 1.4 / 0.75 ** 1.4
    path = np.stack([np.cos(2 * np.pi * turns * t + 2.4) * radius,
                     np.sin(2 * np.pi * turns * t + 2.4) * radius, height], axis=1)
    shadow = np.array(path)
    shadow[:, 2] = 0
    line(shadow, (110, 20, 20), K)
    for i in range(0, len(path), 28):
        line([path[i], shadow[i]], (120, 30, 30), max(1, K // 2))
    line(path, RED, 3 * K)
    for index, colour, size in ((0, RED, 5), (len(path) * 2 // 3, (0, 0, 255), 4)):
        xy, _ = camera.project(path[index])
        cx, cy = xy[0], xy[1] + 0.03 * W
        d.rounded_rectangle([cx - size * K, cy - size * K, cx + size * K, cy + size * K], radius=K, fill=colour)
    # the playback ball, up on the spiral
    xy, _ = camera.project(path[-90])
    cx, cy = xy[0], xy[1] + 0.03 * W
    d.ellipse([cx - 6 * K, cy - 6 * K, cx + 6 * K, cy + 6 * K], fill=RED, outline=(150, 0, 0), width=K)
    # the rim, as on SoundGrain's
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, W - 1, W - 1], fill=255)
    img.putalpha(mask)
    d = ImageDraw.Draw(img)
    d.ellipse([10 * K, 10 * K, W - 10 * K, W - 10 * K], outline=RED, width=3 * K)
    d.ellipse([0, 0, W - 1, W - 1], outline=(0, 0, 0, 255), width=3 * K)
    out = img.resize((SIZE, SIZE), Image.LANCZOS)
    out.save(os.path.join(HERE, "..", "songrande", "SongrandeSplash.png"))


if __name__ == "__main__":
    main()
