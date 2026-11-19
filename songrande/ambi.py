"""
Songrande - Ambisonics math (numpy only, no audio, no GUI).

Conventions, the same as the IEM Plug-in Suite, SPARTA and the author's other
spatial plug-ins (Balloon Palace's Ambi.h, Leitner, openfield): AmbiX, that is
ACN channel order with SN3D normalisation and no Condon-Shortley phase, orders
1 to 7 (4 to 64 channels). Coordinates: x to the front, y to the left, z up;
azimuth turns to the left, elevation goes up.

This file is part of Songrande, a derivative of SoundGrain (Olivier Belanger).
Songrande is free software: you can redistribute it and/or modify it under the
terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.
"""
import json
import math

import numpy as np

MAX_ORDER = 7


def nch(order):
    """Number of Ambisonic channels of an order."""
    return (order + 1) * (order + 1)


def order_for(channels):
    """The highest order that fits in that many channels."""
    order = 0
    while order < MAX_ORDER and nch(order + 1) <= channels:
        order += 1
    return order


def acn_orders(order):
    """The order l of every ACN channel up to 'order'."""
    return np.array([int(math.floor(math.sqrt(n))) for n in range(nch(order))])


def acn_degrees(order):
    """The degree m of every ACN channel up to 'order'."""
    out = []
    for n in range(nch(order)):
        l = int(math.floor(math.sqrt(n)))
        out.append(n - l * l - l)
    return np.array(out)


def _sn3d():
    table = np.zeros((MAX_ORDER + 1, MAX_ORDER + 1))
    for l in range(MAX_ORDER + 1):
        for m in range(l + 1):
            table[l, m] = math.sqrt((1.0 if m == 0 else 2.0) *
                                    math.factorial(l - m) / math.factorial(l + m))
    return table


_SN3D = _sn3d()


def from_azel(az, el):
    """Unit vector(s) from azimuth and elevation in radians."""
    az, el = np.broadcast_arrays(np.asarray(az, dtype=float), np.asarray(el, dtype=float))
    return np.stack([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)], axis=-1)


def to_azel(v):
    """Azimuth and elevation (radians) of vector(s)."""
    v = np.asarray(v, dtype=float)
    az = np.arctan2(v[..., 1], v[..., 0])
    el = np.arctan2(v[..., 2], np.hypot(v[..., 0], v[..., 1]))
    return az, el


def normalise(v):
    v = np.asarray(v, dtype=float)
    length = np.linalg.norm(v, axis=-1, keepdims=True)
    front = np.zeros_like(v)
    front[..., 0] = 1.0
    return np.where(length > 1e-9, v / np.maximum(length, 1e-12), front)


def sh(dirs, order=MAX_ORDER):
    """SN3D real spherical harmonics of unit direction(s), ACN order.

    dirs has shape (..., 3); the result (..., (order + 1)^2). Worked out in
    Cartesian form as in Ambi.h: (x + iy)^m gives cos(m az) and sin(m az) times
    cos(el)^m, and the associated Legendre functions (no Condon-Shortley phase)
    divided by cos(el)^m are polynomials in z built by the usual recurrence.
    """
    order = max(0, min(MAX_ORDER, int(order)))
    d = np.asarray(dirs, dtype=float)
    x, y, z = d[..., 0], d[..., 1], d[..., 2]
    out = np.zeros(d.shape[:-1] + (nch(order),))
    cm = np.ones_like(x)
    sm = np.zeros_like(x)
    qmm = 1.0
    for m in range(order + 1):
        if m > 0:
            cm, sm = cm * x - sm * y, cm * y + sm * x
            qmm *= (2.0 * m - 1.0)
        q2 = 0.0
        q1 = qmm
        for l in range(m, order + 1):
            if l == m:
                q = qmm * np.ones_like(z)
            elif l == m + 1:
                q = z * (2.0 * m + 1.0) * qmm
            else:
                q = ((2.0 * l - 1.0) * z * q1 - (l + m - 1.0) * q2) / float(l - m)
            if l > m:
                q2, q1 = q1, q
            else:
                q1 = q
            nq = _SN3D[l, m] * q
            out[..., l * l + l + m] = nq * cm
            if m > 0:
                out[..., l * l + l - m] = nq * sm
    return out


def maxre(order):
    """max-rE weights of an order (Zotter and Frank): P_l(cos(137.9 deg / (N + 1.51)))."""
    c = math.cos(math.radians(137.9) / (order + 1.51))
    w = []
    p0, p1 = 1.0, c
    for l in range(order + 1):
        if l == 0:
            p = 1.0
        elif l == 1:
            p = c
        else:
            p = ((2.0 * l - 1.0) * c * p1 - (l - 1.0) * p0) / l
            p0, p1 = p1, p
        w.append(p)
    return np.array(w)


def fibonacci(n):
    """n points spread evenly over the sphere (a Fibonacci lattice)."""
    i = np.arange(n)
    golden = math.pi * (3.0 - math.sqrt(5.0))
    z = 1.0 - 2.0 * (i + 0.5) / n
    r = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    a = golden * i
    return np.stack([r * np.cos(a), r * np.sin(a), z], axis=-1)


def order_weights(order, factor):
    """Per-channel weights factor^l: 1 leaves a point, 0 leaves only the omni channel."""
    l = acn_orders(order)
    return np.power(max(0.0, min(1.0, float(factor))), l)


def spread_gain(order, factor):
    """Level make-up when the higher orders fade (half of the lost energy, in dB)."""
    factor = max(0.0, min(1.0, float(factor)))
    full = sum(2 * l + 1 for l in range(order + 1))
    now = sum((2 * l + 1) * factor ** (2 * l) for l in range(order + 1))
    return (full / now) ** 0.25


def encode(pos, order, spread=0.0, near=0.12):
    """Gains of a source at position(s) pos (x front, y left, z up; the unit sphere
    is the loudspeaker sphere). Direction only, the distance model sets the level.

    As in Balloon Palace's encodeNear the higher orders fade as the source nears
    the listener (inside 'near' of the radius), so a sound passing through the
    middle spreads round the head instead of flipping sides; 'spread' (0..1)
    fades them on purpose to make a wide source.
    """
    p = np.asarray(pos, dtype=float)
    r = np.linalg.norm(p, axis=-1)
    y = sh(normalise(p), order)
    factor = np.minimum(1.0, r / max(near, 1e-6)) * (1.0 - max(0.0, min(1.0, spread)))
    l = acn_orders(order)
    weights = np.power(np.asarray(factor)[..., None], l)
    full = sum(2 * k + 1 for k in range(order + 1))
    now = sum((2 * k + 1) * np.asarray(factor) ** (2 * k) for k in range(order + 1))
    makeup = (full / now) ** 0.25
    return y * weights * np.asarray(makeup)[..., None]


def rotate_z(points, angle):
    """Turn point(s) about the vertical axis by angle (radians, to the left)."""
    p = np.asarray(points, dtype=float)
    c, s = math.cos(angle), math.sin(angle)
    out = np.array(p, dtype=float)
    out[..., 0] = c * p[..., 0] - s * p[..., 1]
    out[..., 1] = s * p[..., 0] + c * p[..., 1]
    return out


# ----------------------------------------------------------------------------
# Loudspeaker layouts: (azimuth, elevation) in degrees, azimuth to the left.
# "LFE" entries get no signal.
# ----------------------------------------------------------------------------
LFE = "LFE"

LAYOUTS = {
    "Stereo": [(30, 0), (-30, 0)],
    "Quad": [(45, 0), (-45, 0), (135, 0), (-135, 0)],
    "5.0": [(30, 0), (-30, 0), (0, 0), (110, 0), (-110, 0)],
    "5.1": [(30, 0), (-30, 0), (0, 0), LFE, (110, 0), (-110, 0)],
    "Hexagon": [(30, 0), (-30, 0), (90, 0), (-90, 0), (150, 0), (-150, 0)],
    "7.1": [(30, 0), (-30, 0), (0, 0), LFE, (90, 0), (-90, 0), (150, 0), (-150, 0)],
    "Octagon": [(22.5, 0), (-22.5, 0), (67.5, 0), (-67.5, 0),
                (112.5, 0), (-112.5, 0), (157.5, 0), (-157.5, 0)],
    "Cube": [(45, 35.26), (-45, 35.26), (135, 35.26), (-135, 35.26),
             (45, -35.26), (-45, -35.26), (135, -35.26), (-135, -35.26)],
    "5.1.4": [(30, 0), (-30, 0), (0, 0), LFE, (110, 0), (-110, 0),
              (45, 45), (-45, 45), (135, 45), (-135, 45)],
    "7.1.4": [(30, 0), (-30, 0), (0, 0), LFE, (90, 0), (-90, 0), (150, 0), (-150, 0),
              (45, 45), (-45, 45), (135, 45), (-135, 45)],
    "Dome 8+4+1": [(22.5, 0), (-22.5, 0), (67.5, 0), (-67.5, 0),
                   (112.5, 0), (-112.5, 0), (157.5, 0), (-157.5, 0),
                   (45, 45), (-45, 45), (135, 45), (-135, 45), (0, 90)],
    "Icosahedron": None,  # filled below
    "Sphere 16": None,
    "Sphere 24": None,
}


def _icosahedron():
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    pts = []
    for a in (-1, 1):
        for b in (-phi, phi):
            pts += [(0, a, b), (a, b, 0), (b, 0, a)]
    pts = normalise(np.array(pts, dtype=float))
    # stand it on a vertex pair so one loudspeaker is overhead
    top = pts[np.argmax(pts[:, 2])]
    axis = np.cross(top, [0, 0, 1.0])
    s = np.linalg.norm(axis)
    if s > 1e-9:
        axis /= s
        ang = math.asin(min(1.0, s))
        k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        rot = np.eye(3) + math.sin(ang) * k + (1 - math.cos(ang)) * (k @ k)
        pts = pts @ rot.T
    az, el = to_azel(pts)
    order = np.lexsort((-np.degrees(az), -np.round(np.degrees(el))))
    return [(round(float(np.degrees(az[i])), 2), round(float(np.degrees(el[i])), 2)) for i in order]


def _sphere(n):
    az, el = to_azel(fibonacci(n))
    return [(round(float(np.degrees(a)), 2), round(float(np.degrees(e)), 2)) for a, e in zip(az, el)]


LAYOUTS["Icosahedron"] = _icosahedron()
LAYOUTS["Sphere 16"] = _sphere(16)
LAYOUTS["Sphere 24"] = _sphere(24)

LAYOUT_NAMES = ["Stereo", "Quad", "5.0", "5.1", "Hexagon", "7.1", "Octagon", "Cube",
                "5.1.4", "7.1.4", "Dome 8+4+1", "Icosahedron", "Sphere 16", "Sphere 24"]


def layout_dirs(layout):
    """Unit vectors of a layout's loudspeakers (None for an LFE)."""
    out = []
    for entry in layout:
        if entry == LFE or entry is None:
            out.append(None)
        else:
            out.append(from_azel(math.radians(entry[0]), math.radians(entry[1])))
    return out


def load_iem_layout(path):
    """Read a loudspeaker layout from an IEM AllRADecoder / SPARTA style JSON file.

    Returns a list of (azimuth, elevation) in degrees ordered by channel;
    imaginary loudspeakers are left out.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    speakers = None
    if isinstance(data, dict):
        node = data.get("LoudspeakerLayout", data)
        speakers = node.get("Loudspeakers") if isinstance(node, dict) else None
        if speakers is None and "Decoder" in data:
            speakers = data.get("LoudspeakerLayout", {}).get("Loudspeakers")
    elif isinstance(data, list):
        speakers = data
    if not speakers:
        raise ValueError("No loudspeakers found in %s" % path)
    rows = []
    for index, spk in enumerate(speakers):
        if isinstance(spk, dict):
            if spk.get("IsImaginary", False):
                continue
            channel = int(spk.get("Channel", index + 1))
            rows.append((channel, float(spk.get("Azimuth", 0.0)), float(spk.get("Elevation", 0.0))))
        else:
            rows.append((index + 1, float(spk[0]), float(spk[1])))
    rows.sort()
    top = rows[-1][0]
    layout = [LFE] * top
    for channel, az, el in rows:
        layout[channel - 1] = (az, el)
    return layout


# ----------------------------------------------------------------------------
# Decoders
# ----------------------------------------------------------------------------
def sampling_decoder(dirs, order):
    """Decoder to virtual directions with max-rE weighting, scaled so that a plane
    wave from anywhere puts unit energy across them (Ambi.h samplingDecoder)."""
    dirs = np.asarray(dirs, dtype=float)
    w = maxre(order)
    e = sum((2 * l + 1) * w[l] * w[l] for l in range(order + 1))
    count = float(len(dirs))
    g = math.sqrt(count / e) / count
    l = acn_orders(order)
    return g * (2 * l + 1) * w[l] * sh(dirs, order)


def _hull_triangles(points):
    """Triangles of the convex hull of points on a sphere, by brute force.

    Good for the few dozen loudspeakers of a layout; no scipy needed.
    """
    n = len(points)
    tris = []
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                normal = np.cross(points[j] - points[i], points[k] - points[i])
                length = np.linalg.norm(normal)
                if length < 1e-9:
                    continue
                normal /= length
                side = (points - points[i]) @ normal
                if np.all(side <= 1e-7) or np.all(side >= -1e-7):
                    tris.append((i, j, k))
    return tris


def vbap(points, targets):
    """VBAP gains (len(targets), len(points)) over the convex hull of 'points'."""
    points = np.asarray(points, dtype=float)
    targets = np.asarray(targets, dtype=float)
    tris = _hull_triangles(points)
    gains = np.zeros((len(targets), len(points)))
    best = np.full(len(targets), -np.inf)
    for (i, j, k) in tris:
        base = np.stack([points[i], points[j], points[k]], axis=1)
        if abs(np.linalg.det(base)) < 1e-9:
            continue
        g = np.linalg.solve(base, targets.T).T
        low = g.min(axis=1)
        pick = (low > -1e-6) & (low > best)
        if not np.any(pick):
            continue
        gg = np.maximum(g[pick], 0.0)
        norm = np.linalg.norm(gg, axis=1, keepdims=True)
        gg = gg / np.maximum(norm, 1e-12)
        rows = np.nonzero(pick)[0]
        gains[rows] = 0.0
        gains[rows, i] = gg[:, 0]
        gains[rows, j] = gg[:, 1]
        gains[rows, k] = gg[:, 2]
        best[rows] = low[pick]
    return gains, tris


def allrad(layout, order, virtual=None):
    """All-round Ambisonic decoder (Zotter and Frank) for a loudspeaker layout.

    The scene is decoded to a dense even set of virtual loudspeakers with max-rE
    weights, and each of those is panned to the real ones with VBAP. Where the
    layout leaves the floor or the ceiling open an imaginary loudspeaker closes
    the hull and its signal is shared among its neighbours, as the IEM
    AllRADecoder does. Returns a matrix (loudspeakers, channels); LFE rows are 0.
    """
    dirs = layout_dirs(layout)
    real = [i for i, d in enumerate(dirs) if d is not None]
    count = len(dirs)
    matrix = np.zeros((count, nch(order)))
    if not real:
        return matrix
    pts = np.array([dirs[i] for i in real])
    if len(real) == 1:
        matrix[real[0], 0] = 1.0
        return matrix
    if len(real) < 4:
        # two or three loudspeakers: virtual cardioid-like microphones towards each
        o = min(order, 1)
        y = sh(pts, o)
        part = np.zeros((len(real), nch(order)))
        part[:, :nch(o)] = 0.5 * y * np.where(acn_orders(o) == 0, 1.0, 1.0)
        matrix[real] = part * math.sqrt(2.0 / len(real))
        return matrix
    els = np.degrees(np.arcsin(np.clip(pts[:, 2], -1, 1)))
    imaginary = []
    if els.min() > -30.0:
        imaginary.append(np.array([0.0, 0.0, -1.0]))
    if els.max() < 30.0:
        imaginary.append(np.array([0.0, 0.0, 1.0]))
    hull = np.vstack([pts] + [im[None, :] for im in imaginary]) if imaginary else pts
    if virtual is None:
        virtual = fibonacci(max(360, 8 * nch(order)))
    gains, tris = vbap(hull, virtual)
    n_real = len(pts)
    for index in range(len(imaginary)):
        col = n_real + index
        neighbours = sorted({v for t in tris if col in t for v in t if v < n_real})
        if neighbours:
            share = gains[:, col:col + 1] / math.sqrt(len(neighbours))
            gains[:, neighbours] = np.sqrt(gains[:, neighbours] ** 2 + share ** 2)
    gains = gains[:, :n_real]
    decode = gains.T @ sampling_decoder(virtual, order)
    # unit energy on average for a plane wave from anywhere
    probe = fibonacci(500)
    energy = np.mean(np.sum((sh(probe, order) @ decode.T) ** 2, axis=1))
    decode /= math.sqrt(max(energy, 1e-12))
    matrix[real] = decode
    return matrix


def stereo_decoder(order):
    """Two virtual cardioids pointing left and right (the W +- Y preview of openfield)."""
    matrix = np.zeros((2, nch(order)))
    matrix[0, 0] = matrix[1, 0] = 0.5 * math.sqrt(2.0)
    if order >= 1:
        matrix[0, 1] = 0.5 * math.sqrt(2.0)
        matrix[1, 1] = -0.5 * math.sqrt(2.0)
    return matrix


# ----------------------------------------------------------------------------
# Analysis (used by the tests and the self-test)
# ----------------------------------------------------------------------------
def intensity_vector(bformat):
    """Direction the energy comes from, out of the first four AmbiX channels.

    bformat: array (4+, frames) in ACN/SN3D (W, Y, Z, X). Returns the unit
    vector (x, y, z) and the mean-square of W.
    """
    b = np.asarray(bformat, dtype=float)
    w, y, z, x = b[0], b[1], b[2], b[3]
    vec = np.array([np.mean(w * x), np.mean(w * y), np.mean(w * z)])
    power = float(np.mean(w * w))
    length = np.linalg.norm(vec)
    if length < 1e-15:
        return np.zeros(3), power
    return vec / length, power


def energy_vector(gains, dirs):
    """Gerzon's energy vector of loudspeaker gains (or mean-square levels) at dirs."""
    g = np.asarray(gains, dtype=float)
    d = np.asarray(dirs, dtype=float)
    e = g * g
    total = e.sum()
    if total < 1e-15:
        return np.zeros(3)
    return (e[:, None] * d).sum(axis=0) / total


# ----------------------------------------------------------------------------
# Binaural: Ambisonics to headphones
# ----------------------------------------------------------------------------
def kemar_hrirs(tables):
    """The MIT KEMAR set (Gardner and Martin, 1994) that ships inside pyo, as arrays.

    tables: (IR_LEFT, IR_RIGHT) from pyo.lib.hrtf.ImpulseResponseTables().getTables():
    14 elevations from -40 to +90 degrees, azimuths from 0 to 180 degrees to the
    right. The left half-space is made by swapping the ears, so the head is
    exactly symmetric. Returns unit vectors (n, 3) and left-ear responses (n, taps).
    """
    left, right = tables
    dirs, irs = [], []
    for e, (row_l, row_r) in enumerate(zip(left, right)):
        el = math.radians((e - 4) * 10.0)
        count = len(row_l)
        for a in range(count):
            az_right = math.pi * a / (count - 1) if count > 1 else 0.0
            # source on the right: Ambisonic azimuth is negative there
            dirs.append(from_azel(-az_right, el))
            irs.append(np.asarray(row_l[a], dtype=float))
            if 0 < a < count - 1:
                # the mirrored source on the left: the left ear hears what the right ear heard
                dirs.append(from_azel(az_right, el))
                irs.append(np.asarray(row_r[a], dtype=float))
    return np.array(dirs), np.array(irs)


def _resample(irs, ratio):
    """Band-limited resampling of impulse responses along the last axis."""
    if abs(ratio - 1.0) < 1e-6:
        return irs
    n = irs.shape[-1]
    m = int(round(n * ratio))
    spec = np.fft.rfft(irs, axis=-1)
    out = np.zeros(irs.shape[:-1] + (m // 2 + 1,), dtype=complex)
    k = min(spec.shape[-1], out.shape[-1])
    out[..., :k] = spec[..., :k]
    # irfft divides by m, so the sum of the taps (the gain at 0 Hz) stays what it was
    return np.fft.irfft(out, n=m, axis=-1)


def binaural_filters(order, tables, sr=44100.0, taps=96, crossover=1500.0):
    """FIR filters that turn an AmbiX scene into the left ear's signal.

    Magnitude least squares (Schoerkhuber, Zaunschirm and Hoeldrich 2018, the
    method behind the IEM BinauralDecoder): below the crossover the head-related
    transfer functions are fitted to the spherical harmonics as they are; above
    it only their magnitudes are, the phase being carried on from the bin below,
    which keeps the highs that a plain low-order fit loses. A diffuse-field
    equalisation then restores the average colour of the measured set.

    Returns (filters, signs): filters (channels, taps) for the left ear; the
    right ear, the head being symmetric, uses the same filters with the sign of
    every sine harmonic (m < 0) flipped.
    """
    order = max(0, min(3, int(order)))
    dirs, irs = kemar_hrirs(tables)
    if abs(sr - 44100.0) > 1.0:
        irs = _resample(irs, sr / 44100.0)
    n = irs.shape[1]
    nfft = 1
    while nfft < 2 * n:
        nfft *= 2
    spec = np.fft.rfft(irs, n=nfft, axis=1)              # (dirs, bins)
    # the measured set stops at -40 degrees: stand in for the floor with the
    # lowest ring so the fit can't run wild down there
    low = dirs[:, 2] < math.sin(math.radians(-35.0))
    extra_dirs, extra_spec = [], []
    az_low, _ = to_azel(dirs[low])
    for el in (-55.0, -70.0, -85.0):
        extra_dirs.append(from_azel(az_low, math.radians(el)))
        extra_spec.append(spec[low])
    all_dirs = np.vstack([dirs] + extra_dirs)
    all_spec = np.vstack([spec] + extra_spec)
    y = sh(all_dirs, order)                               # (dirs, channels)
    # weight by the solid angle each measurement stands for (rings near the pole are dense)
    weight = np.ones(len(all_dirs))
    rings = np.round(np.degrees(np.arcsin(np.clip(all_dirs[:, 2], -1, 1))))
    for ring in np.unique(rings):
        members = rings == ring
        weight[members] = max(math.cos(math.radians(ring)), 0.05) / members.sum()
    weight /= weight.sum()
    sw = np.sqrt(weight)[:, None]
    pinv = np.linalg.pinv(y * sw, rcond=1e-3)              # (channels, dirs)
    bins = spec.shape[1]
    kc = int(round(crossover / (sr / nfft)))
    coef = np.zeros((nch(order), bins), dtype=complex)
    for k in range(bins):
        target = all_spec[:, k]
        if k > kc:
            phase = np.angle(y @ coef[:, k - 1])
            target = np.abs(target) * np.exp(1j * phase)
        coef[:, k] = pinv @ (target * sw[:, 0])
    # diffuse-field equalisation over the measured directions
    got = np.abs(sh(dirs, order) @ coef) ** 2             # (dirs, bins)
    want = np.abs(spec) ** 2
    w0 = weight[:len(dirs)] / weight[:len(dirs)].sum()
    eq = np.sqrt((w0[:, None] * want).sum(axis=0) / np.maximum((w0[:, None] * got).sum(axis=0), 1e-12))
    eq = np.clip(eq, 0.5, 2.5)
    coef *= eq[None, :]
    # the carried-on phase can put part of a response before time zero: delay
    # everything by a quarter of the block so it does not wrap round
    shift = nfft // 4
    coef = coef * np.exp(-2j * math.pi * np.arange(bins) * shift / nfft)[None, :]
    filters = np.fft.irfft(coef, n=nfft, axis=1)
    # keep the part that carries the energy, with a short fade at each end
    energy = (filters ** 2).sum(axis=0)
    cum = np.cumsum(energy)
    start = int(np.searchsorted(cum, 0.002 * cum[-1]))
    start = max(0, start - 2)
    taps = int(min(round(taps * sr / 44100.0), nfft - start))
    cut = np.array(filters[:, start:start + taps])
    fade = max(4, taps // 8)
    cut[:, -fade:] *= 0.5 * (1.0 + np.cos(np.linspace(0, math.pi, fade)))
    cut[:, :2] *= np.array([0.5, 1.0])[None, :]
    # level: an ear hears a sound from anywhere at unity on average
    level = np.mean(np.sum((sh(dirs, order) @ cut) ** 2, axis=1) * w0) * len(w0) / len(w0)
    level = float(np.sum(np.sum((sh(dirs, order) @ cut) ** 2, axis=1) * w0))
    cut /= math.sqrt(max(level, 1e-12))
    signs = np.where(acn_degrees(order) < 0, -1.0, 1.0)
    return cut, signs


def binaural_render(filters, signs, bus):
    """Offline reference of the binaural decoder: bus (channels, frames) -> (2, frames)."""
    count = min(len(filters), len(bus))
    frames = bus.shape[1]
    left = np.zeros(frames + filters.shape[1] - 1)
    right = np.zeros_like(left)
    for c in range(count):
        y = np.convolve(bus[c], filters[c])
        left += y
        right += signs[c] * y
    return np.stack([left[:frames], right[:frames]])
