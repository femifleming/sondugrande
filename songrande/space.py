"""
Songrande - the geometry of the room: coordinates, camera, pointer rays,
distance cues and the mapping from a point in space to SoundGrain's X and Y.
No GUI and no audio in here, so everything can be tested headless.

Three coordinate frames are used:

* canvas  (cx, cy, cz): what trajectories are stored in. It is SoundGrain's
  drawing surface laid on the floor of the room, 1000 x 1000 units, plus a
  height: cx runs left to right (the sound file from start to end), cy runs
  from the front wall (0) to the back wall (1000), exactly as SoundGrain's
  pixels ran from the top of the window to the bottom, and cz is the height
  above ear level (negative below). 500 units are one radius of the
  loudspeaker sphere.
* room    (right, front, up): the same thing centred on the listener and in
  units of the sphere's radius. This is what the 3D view draws.
* ambi    (x front, y left, z up): the Ambisonic convention of ambi.py.

This file is part of Songrande, a derivative of SoundGrain (Olivier Belanger),
released under the GNU General Public License version 3 or later.
"""
import math

import numpy as np

CANVAS = 1000.0          # width and depth of the floor in canvas units
HALF = CANVAS / 2.0      # canvas units per sphere radius
HEIGHT = 500.0           # how far up and down the pen may go
SPEED_OF_SOUND = 343.0


# ----------------------------------------------------------------------------
# coordinates
# ----------------------------------------------------------------------------
def canvas_to_room(points):
    p = np.asarray(points, dtype=float)
    out = np.empty(p.shape[:-1] + (3,))
    out[..., 0] = (p[..., 0] - HALF) / HALF
    out[..., 1] = (HALF - p[..., 1]) / HALF
    out[..., 2] = (p[..., 2] if p.shape[-1] > 2 else 0.0) / HALF
    return out


def room_to_canvas(points):
    p = np.asarray(points, dtype=float)
    out = np.empty(p.shape[:-1] + (3,))
    out[..., 0] = p[..., 0] * HALF + HALF
    out[..., 1] = HALF - p[..., 1] * HALF
    out[..., 2] = p[..., 2] * HALF
    return out


def room_to_ambi(points):
    p = np.asarray(points, dtype=float)
    out = np.empty(p.shape)
    out[..., 0] = p[..., 1]
    out[..., 1] = -p[..., 0]
    out[..., 2] = p[..., 2]
    return out


def ambi_to_room(points):
    p = np.asarray(points, dtype=float)
    out = np.empty(p.shape)
    out[..., 0] = -p[..., 1]
    out[..., 1] = p[..., 0]
    out[..., 2] = p[..., 2]
    return out


def canvas_to_ambi(points):
    return room_to_ambi(canvas_to_room(points))


def azel_dist(room_point):
    """Azimuth (degrees, to the left), elevation (degrees) and distance (radii)."""
    r, f, u = float(room_point[0]), float(room_point[1]), float(room_point[2])
    dist = math.sqrt(r * r + f * f + u * u)
    az = math.degrees(math.atan2(-r, f))
    el = math.degrees(math.atan2(u, math.hypot(r, f)))
    return az, el, dist


def clip_canvas(point):
    """Keep a canvas point inside the room."""
    x = min(max(point[0], 0.0), CANVAS)
    y = min(max(point[1], 0.0), CANVAS)
    z = min(max(point[2] if len(point) > 2 else 0.0, -HEIGHT), HEIGHT)
    return (x, y, z)


# ----------------------------------------------------------------------------
# what SoundGrain's X (place in the sound) and Y (the Y-axis parameters) read
# ----------------------------------------------------------------------------
X_SOURCES = ["Left - right", "Azimuth", "Along the path", "Height"]
Y_SOURCES = ["Front - back", "Height", "Distance", "Elevation"]


def grain_xy(canvas_point, phase, x_source=0, y_source=0):
    """SoundGrain's normalised (x, y) of a point of a trajectory.

    x picks the place in the sound file and y drives the Y-axis parameters.
    With the default sources the floor of the room IS SoundGrain's surface:
    left to right is the sound from start to end, back to front is Y from 0 to 1.
    phase is how far along the trajectory the point is (0..1).
    """
    cx, cy, cz = canvas_point[0], canvas_point[1], canvas_point[2] if len(canvas_point) > 2 else 0.0
    room = ((cx - HALF) / HALF, (HALF - cy) / HALF, cz / HALF)
    if x_source == 1:
        x = (math.atan2(room[0], room[1]) / (2.0 * math.pi)) % 1.0     # clockwise from the front
    elif x_source == 2:
        x = phase
    elif x_source == 3:
        x = cz / (2.0 * HEIGHT) + 0.5
    else:
        x = cx / CANVAS
    if y_source == 1:
        y = cz / (2.0 * HEIGHT) + 0.5
    elif y_source == 2:
        y = math.sqrt(room[0] ** 2 + room[1] ** 2 + room[2] ** 2) / math.sqrt(2.0)
    elif y_source == 3:
        y = math.atan2(room[2], math.hypot(room[0], room[1])) / math.pi + 0.5
    else:
        y = 1.0 - cy / CANVAS
    return min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)


# ----------------------------------------------------------------------------
# distance cues (after Balloon Palace's Distance.h, itself after the IEM RoomEncoder)
# ----------------------------------------------------------------------------
def distance_cues(dist, room_m=5.0, rolloff=1.0, air=0.5, doppler=1.0):
    """Level, propagation delay (s) and air-absorption cutoff (Hz) of a source.

    dist is in radii of the loudspeaker sphere, room_m how many metres one
    radius is. On the sphere the level is 1; inside it rises (never more than
    +12 dB), outside it falls as 1 / distance ^ rolloff.
    """
    d = max(float(dist), 0.0)
    gain = min(4.0, (1.0 / max(d, 0.25)) ** max(0.0, rolloff))
    metres = d * room_m
    delay = doppler * metres / SPEED_OF_SOUND
    cutoff = 20000.0 / (1.0 + air * metres / 12.5)
    return gain, delay, cutoff


def scatter_ring(ambi_pos, angle, count, turn=0.0, wobble=None):
    """'count' points round a source, 'angle' radians away from it as seen from
    the listener and at its distance: where the grains of one stream land.

    turn rotates the ring about the line of sight; wobble (count values 0..1)
    pulls single points inward so the ring fills in over time.
    """
    p = np.asarray(ambi_pos, dtype=float)
    dist = float(np.linalg.norm(p))
    if dist < 1e-6 or angle <= 1e-6:
        return np.repeat(p[None, :], count, axis=0)
    axis = p / dist
    helper = np.array([0.0, 0.0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(axis, helper)
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    out = np.empty((count, 3))
    for k in range(count):
        a = angle * (1.0 if wobble is None else 0.35 + 0.65 * wobble[k])
        theta = turn + 2.0 * math.pi * k / count
        direction = math.cos(a) * axis + math.sin(a) * (math.cos(theta) * u + math.sin(theta) * v)
        out[k] = direction * dist
    return out


# ----------------------------------------------------------------------------
# camera
# ----------------------------------------------------------------------------
VIEWS = ["3D", "Top", "Front", "Side"]


class Camera:
    """An orbiting camera looking at the listener, or one of three flat views.

    Works in room coordinates (right, front, up). project() gives screen pixels
    and a depth; ray() turns a pixel back into a line in the room.
    """

    def __init__(self):
        self.view = "3D"
        self.yaw = math.radians(-28.0)      # turned about the vertical, + is counter-clockwise from above
        self.pitch = math.radians(32.0)     # looking down from this far above the floor
        self.distance = 5.2                 # from the listener, in radii
        self.zoom = 1.0
        self.fov = math.radians(38.0)
        self.width = 800
        self.height = 600

    def setSize(self, width, height):
        self.width, self.height = max(1, int(width)), max(1, int(height))

    def setView(self, view):
        if view in VIEWS:
            self.view = view

    def reset(self):
        view = self.view
        self.__init__()
        self.view = view

    def orbit(self, dx, dy):
        self.yaw -= dx * 0.008
        self.pitch = min(max(self.pitch + dy * 0.008, math.radians(-89.0)), math.radians(89.0))

    def dolly(self, steps):
        self.zoom = min(max(self.zoom * (1.12 ** steps), 0.3), 12.0)

    def getState(self):
        return {"view": self.view, "yaw": self.yaw, "pitch": self.pitch, "zoom": self.zoom}

    def setState(self, state):
        self.setView(state.get("view", "3D"))
        self.yaw = float(state.get("yaw", self.yaw))
        self.pitch = float(state.get("pitch", self.pitch))
        self.zoom = float(state.get("zoom", self.zoom))

    def basis(self):
        """The camera's right, up and forward (into the screen) unit vectors."""
        if self.view == "Top":
            return np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, -1.0])
        if self.view == "Front":       # standing at the back wall looking forward
            return np.array([1.0, 0, 0]), np.array([0, 0, 1.0]), np.array([0, 1.0, 0])
        if self.view == "Side":        # standing at the left wall looking right
            return np.array([0, -1.0, 0]), np.array([0, 0, 1.0]), np.array([1.0, 0, 0])
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        forward = np.array([-sy * cp, cy * cp, -sp])
        right = np.array([cy, sy, 0.0])
        up = np.cross(right, forward)
        return right, up, forward

    def isOrtho(self):
        return self.view != "3D"

    def scale(self):
        """Pixels per radius at the listener."""
        base = min(self.width, self.height)
        if self.isOrtho():
            return base * 0.40 * self.zoom
        return base * 0.5 / math.tan(self.fov / 2.0) / self.distance * self.zoom

    def eye(self):
        right, up, forward = self.basis()
        return -forward * self.distance

    def project(self, points):
        """Room points (..., 3) -> (screen xy (..., 2), depth (...))."""
        p = np.asarray(points, dtype=float)
        right, up, forward = self.basis()
        x = p @ right
        y = p @ up
        z = p @ forward
        if self.isOrtho():
            s = self.scale()
            sx = self.width / 2.0 + x * s
            sy = self.height / 2.0 - y * s
            return np.stack([sx, sy], axis=-1), z
        depth = z + self.distance
        f = min(self.width, self.height) * 0.5 / math.tan(self.fov / 2.0) * self.zoom
        d = np.maximum(depth, 0.05)
        sx = self.width / 2.0 + x * f / d
        sy = self.height / 2.0 - y * f / d
        return np.stack([sx, sy], axis=-1), depth

    def pixelsPerUnit(self, point):
        """How many pixels one radius covers at a room point."""
        if self.isOrtho():
            return self.scale()
        right, up, forward = self.basis()
        depth = max(float(np.dot(np.asarray(point, dtype=float), forward)) + self.distance, 0.05)
        return min(self.width, self.height) * 0.5 / math.tan(self.fov / 2.0) * self.zoom / depth

    def ray(self, sx, sy):
        """The line under a pixel: (origin, unit direction) in room coordinates."""
        right, up, forward = self.basis()
        if self.isOrtho():
            s = self.scale()
            origin = right * ((sx - self.width / 2.0) / s) + up * ((self.height / 2.0 - sy) / s) - forward * 50.0
            return origin, forward.copy()
        f = min(self.width, self.height) * 0.5 / math.tan(self.fov / 2.0) * self.zoom
        direction = forward * f + right * (sx - self.width / 2.0) + up * (self.height / 2.0 - sy)
        direction /= np.linalg.norm(direction)
        return self.eye(), direction


def ray_plane(origin, direction, point, normal):
    """Where a ray meets a plane (None if it runs along it or the plane is behind)."""
    denom = float(np.dot(direction, normal))
    if abs(denom) < 1e-6:
        return None
    t = float(np.dot(np.asarray(point, dtype=float) - origin, normal)) / denom
    if t < 0:
        return None
    return origin + direction * t


def ray_sphere(origin, direction, radius, far=False, centre=(0.0, 0.0, 0.0)):
    """Where a ray meets a sphere: the near side, or the far (inner) side.

    If the ray misses, the point of the sphere's outline nearest to it is
    returned, so the pen slides round the edge instead of jumping away.
    """
    centre = np.asarray(centre, dtype=float)
    oc = origin - centre
    b = float(np.dot(oc, direction))
    c = float(np.dot(oc, oc)) - radius * radius
    disc = b * b - c
    if disc < 0:
        closest = origin - direction * b
        offset = closest - centre
        length = np.linalg.norm(offset)
        if length < 1e-9:
            return None
        return centre + offset / length * radius
    root = math.sqrt(disc)
    t = -b + root if far else -b - root
    if t < 0:
        t = -b + root
        if t < 0:
            return None
    return origin + direction * t


def closest_on_axis(origin, direction, point, axis):
    """The parameter s of the point on the line (point + s * axis) nearest to a ray."""
    axis = np.asarray(axis, dtype=float)
    w = origin - np.asarray(point, dtype=float)
    a = float(np.dot(direction, direction))
    b = float(np.dot(direction, axis))
    c = float(np.dot(axis, axis))
    d = float(np.dot(direction, w))
    e = float(np.dot(axis, w))
    denom = a * c - b * b
    if abs(denom) < 1e-9:
        return 0.0
    return (a * e - b * d) / denom
