#!/usr/bin/env python
# encoding: utf-8
"""
Copyright 2009-2017 Olivier Belanger (SoundGrain)
Songrande additions: trajectories in three dimensions.

This file is part of Songrande, a derivative of SoundGrain.

Songrande is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Songrande is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Songrande.  If not, see <http://www.gnu.org/licenses/>.

A trajectory is SoundGrain's trajectory with a third coordinate: its points
are (x, y, z) in canvas units (see space.py). x and y are SoundGrain's own
surface, now the floor of the room, and z is the height above ear level. The
class holds no GUI object, so it runs without a display (tests, offline
rendering); the 3D surface keeps the pens and brushes.
"""
import random
from math import sin, cos, pi, sqrt, floor

from .Biquad_Filter import BiquadLP
from .space import CANVAS, HEIGHT

DIRECTIONS = ["Forward", "Backward", "Back and forth"]


def chooseColour(i, numlines=24):
    """SoundGrain's trajectory colours, as (object rgb, label rgb) tuples."""
    def clip(x):
        val = int(x * 255)
        return 0 if val < 0 else 255 if val > 255 else val

    def colour(i, numlines, sat, bright):
        hue = (i / float(numlines)) * 180 + 15
        segment = floor(hue / 60) % 6
        fraction = hue / 60 - segment
        t1 = bright * (1 - sat)
        t2 = bright * (1 - (sat * fraction))
        t3 = bright * (1 - (sat * (1 - fraction)))
        if segment == 0:
            r, g, b = bright, t3, t1
        elif segment == 1:
            r, g, b = t2, bright, t1
        elif segment == 2:
            r, g, b = t1, bright, t3
        elif segment == 3:
            r, g, b = t1, t2, bright
        elif segment == 4:
            r, g, b = t3, t1, bright
        else:
            r, g, b = bright, t1, t2
        return (clip(r), clip(g), clip(b))

    labelColour = colour(i, numlines, 1, 1)
    objectColour = colour(i, numlines, .85, .75)
    return objectColour, labelColour


def _p3(point):
    """A point as a 3-tuple of floats (a 2D point lies at ear level)."""
    if len(point) > 2:
        return (float(point[0]), float(point[1]), float(point[2]))
    return (float(point[0]), float(point[1]), 0.0)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _length(v):
    return sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def onSphere(point, radius):
    """A canvas point moved along its line to the listener onto the sphere of
    that radius (in radii of the loudspeaker sphere)."""
    room = (point[0] - CANVAS / 2.0, CANVAS / 2.0 - point[1], point[2])
    length = _length(room)
    if length < 1e-6:
        return point
    k = radius * (CANVAS / 2.0) / length
    return (room[0] * k + CANVAS / 2.0, CANVAS / 2.0 - room[1] * k, room[2] * k)


class Trajectory:
    def __init__(self, owner, label):
        # owner: whatever holds the sound engine in its 'audio' attribute (the
        # scene); the engine is told about speed, transposition and activity
        self.owner = owner
        self.label = label
        self.id = int(self.label) - 1
        self.colour, self.bordercolour = chooseColour(int(self.label) - 1)
        self.activeLp = True
        self.editLevel = 2
        self.timeSpeed = 25
        self.amplitude = 1
        self.type = None
        self.center = None
        self.radius = None
        self.basis = None          # the plane a circle / oscil / spiral was drawn in: (u, v, w)
        self.sphere = None         # radius (in radii) of the sphere a shape was drawn on, if any
        self.active = False
        self.freeze = False
        self.initPoints = []
        self.points = []
        self.mario = 0
        self.lastCirclePos = (0, 0, 0)
        self.circlePos = None
        self.counter = 0
        self.lastIndex = 0
        self.filterCut = 5000
        self.step = 1
        self.direction = 0
        self.lpx = BiquadLP()
        self.lpy = BiquadLP()
        self.lpz = BiquadLP()
        self.transpo = 1
        self.width = 2
        self.wanderSpeed = 1.0
        self.wanderPeriodicity = 0.0
        self.closed = False
        self.geometryTransformed = False
        self._random = random.Random()
        self.resetWander()

    @property
    def audio(self):
        return getattr(self.owner, "audio", None)

    # ------------------------------------------------------------------
    # width and variation (SoundGrain's "Var" tab), now a tube round the path
    # ------------------------------------------------------------------
    def setWidth(self, width):
        self.width = max(2, min(500, int(width)))
        if self.circlePos is not None and self.points:
            index = self.lastIndex % len(self.points)
            self.circlePos = self._displacedPoint(index, advance=False)

    def getWidth(self):
        return self.width

    def setWanderSpeed(self, speed):
        self.wanderSpeed = max(0.1, min(10.0, float(speed)))

    def getWanderSpeed(self):
        return self.wanderSpeed

    def setWanderPeriodicity(self, value):
        self.wanderPeriodicity = max(0.0, min(1.0, float(value)))
        if self.circlePos is not None and self.points:
            index = self.lastIndex % len(self.points)
            self.circlePos = self._displacedPoint(index, advance=False)

    def getWanderPeriodicity(self):
        return self.wanderPeriodicity

    def resetWander(self):
        self._wanderPhase = 0.0
        self._wanderStart = [0.0, 0.0]
        self._wanderTarget = [self._random.uniform(-1.0, 1.0), self._random.uniform(-1.0, 1.0)]
        self._wanderElapsed = 0.0
        self._wanderDuration = self._random.uniform(0.4, 1.2)
        self._normal = None

    def _advanceWander(self):
        # Use playback time, so freeze pauses the noise and timer changes do
        # not turn a smooth drift into rapid jitter.
        elapsed = self.timeSpeed * 0.001 * self.wanderSpeed
        # One sine cycle spans two average random transitions at normal speed.
        self._wanderPhase = (self._wanderPhase + elapsed / 1.6) % 1.0
        self._wanderElapsed += elapsed
        while self._wanderElapsed >= self._wanderDuration:
            self._wanderElapsed -= self._wanderDuration
            self._wanderStart = list(self._wanderTarget)
            self._wanderTarget = [self._random.uniform(-1.0, 1.0), self._random.uniform(-1.0, 1.0)]
            self._wanderDuration = self._random.uniform(0.4, 1.2)
        return self._wanderValue()

    def _wanderValue(self):
        """Two offsets in [-1, 1]: across the path and, a quarter turn later, the other way."""
        phase = self._wanderElapsed / self._wanderDuration
        blend = phase * phase * (3.0 - 2.0 * phase)
        out = []
        for axis in range(2):
            noise = self._wanderStart[axis] + (self._wanderTarget[axis] - self._wanderStart[axis]) * blend
            wave = sin(2 * pi * self._wanderPhase) if axis == 0 else cos(2 * pi * self._wanderPhase)
            # A convex blend stays inside [-1, 1] at every periodicity setting.
            out.append(wave * (1 - self.wanderPeriodicity) + noise * self.wanderPeriodicity)
        return out

    def _tangent(self, index):
        # Average nearby segment directions, ignoring repeated points. Open
        # endpoints use only their own side; closed paths wrap at the seam.
        count = len(self.points)
        d = [0.0, 0.0, 0.0]
        for offset in range(-3, 3):
            a = index + offset
            b = a + 1
            if not self.closed and (a < 0 or b >= count):
                continue
            s = _sub(self.points[b % count], self.points[a % count])
            length = _length(s)
            if length > 0:
                weight = 3 - min(abs(offset), abs(offset + 1))
                for k in range(3):
                    d[k] += s[k] / length * weight
        length = _length(d)
        if length < 1e-9:
            return None
        return (d[0] / length, d[1] / length, d[2] / length)

    def _getNormal(self, index, previous=None):
        """The level perpendicular of the path at a point (SoundGrain's 2D normal
        when the path lies flat), kept from flipping when the path doubles back."""
        t = self._tangent(index)
        if t is None:
            return previous or (0.0, 1.0, 0.0)
        flat = sqrt(t[0] * t[0] + t[1] * t[1])
        if flat < 1e-6:
            normal = previous or (1.0, 0.0, 0.0)
            # keep it square to a vertical stretch of path
            normal = (normal[0], normal[1], 0.0)
            length = _length(normal) or 1.0
            return (normal[0] / length, normal[1] / length, 0.0)
        normal = (-t[1] / flat, t[0] / flat, 0.0)
        if previous and sum(a * b for a, b in zip(normal, previous)) < 0:
            normal = (-normal[0], -normal[1], 0.0)
        return normal

    def _displacedPoint(self, index, advance=True):
        point = self.points[index]
        if self.width <= 2:
            return point
        n1 = self._getNormal(index, self._normal)
        self._normal = n1
        t = self._tangent(index) or (1.0, 0.0, 0.0)
        n2 = _cross(t, n1)
        length = _length(n2)
        n2 = (n2[0] / length, n2[1] / length, n2[2] / length) if length > 1e-9 else (0.0, 0.0, 1.0)
        radius = (self.width - 2) * 0.5
        a, b = self._advanceWander() if advance else self._wanderValue()
        # a flat path keeps SoundGrain's side to side sweep; the second axis
        # lifts it off the floor, so with a periodic variation it corkscrews
        scale = 1.0 / max(1.0, sqrt(a * a + b * b))
        a, b = a * scale * radius, b * scale * radius
        moved = [point[k] + n1[k] * a + n2[k] * b for k in range(3)]
        # stay in the room without bending the offset: shrink it
        factor = 1.0
        limits = ((0.0, CANVAS), (0.0, CANVAS), (-HEIGHT, HEIGHT))
        for k in range(3):
            delta = moved[k] - point[k]
            low, high = limits[k]
            if delta > 1e-9 and moved[k] > high:
                factor = min(factor, max(0.0, (high - point[k]) / delta))
            elif delta < -1e-9 and moved[k] < low:
                factor = min(factor, max(0.0, (low - point[k]) / delta))
        return tuple(min(max(point[k] + (moved[k] - point[k]) * factor, limits[k][0]), limits[k][1])
                     for k in range(3))

    # ------------------------------------------------------------------
    def clear(self):
        self.setWidth(2)
        self.setWanderSpeed(1)
        self.setWanderPeriodicity(0)
        self.resetWander()
        self.closed = False
        self.geometryTransformed = False
        self.type = None
        self.center = None
        self.radius = None
        self.basis = None
        self.sphere = None
        self.direction = 0
        self.setActive(False)
        self.initPoints = []
        self.points = []
        self.circlePos = None
        self.setTranspo(1.)

    def getAttributes(self):
        return {'width': self.width,
                'geometryTransformed': self.geometryTransformed,
                'wanderSpeed': self.wanderSpeed,
                'wanderPeriodicity': self.wanderPeriodicity,
                'closed': self.closed,
                'activeLp': self.activeLp,
                'editLevel': self.editLevel,
                'timeSpeed': self.timeSpeed,
                'amplitude': self.amplitude,
                'step': self.step,
                'direction': self.direction,
                'type': self.type,
                'center': self.center,
                'radius': self.radius,
                'basis': self.basis,
                'sphere': self.sphere,
                'active': self.active,
                'freeze': self.freeze,
                'circlePos': self.circlePos,
                'counter': self.counter,
                'filterCut': self.filterCut,
                'points': [list(p) for p in self.getPoints()]}

    def setAttributes(self, dict, xfac=1.0, yfac=1.0, zfac=1.0):
        """Restore a trajectory. A SoundGrain (2D) trajectory comes in with x and y
        only; xfac and yfac scale its window to the floor of the room."""
        self.setWidth(dict.get('width', 2))
        self.setWanderSpeed(dict.get('wanderSpeed', 1))
        self.setWanderPeriodicity(dict.get('wanderPeriodicity', 0))
        self.closed = dict.get('closed', dict.get('type') == 'circle')
        self.geometryTransformed = dict.get('geometryTransformed', False)
        self.activeLp = dict['activeLp']
        self.editLevel = dict['editLevel']
        self.setTimeSpeed(dict['timeSpeed'])
        self.setAmplitude(dict.get('amplitude', 1.0))
        self.step = dict['step']
        self.direction = int(dict.get('direction', 0))
        self.setActive(dict['active'])
        self.freeze = dict['freeze']
        self.counter = dict['counter']
        self.filterCut = dict['filterCut']
        self.setPoints(dict['points'], xfac=xfac, yfac=yfac, zfac=zfac)
        self.type = dict['type']
        self.basis = dict.get('basis')
        self.sphere = dict.get('sphere')
        if self.basis is not None:
            self.basis = [tuple(v) for v in self.basis]
        centre = dict.get('center')
        if self.getType() in ['circle', 'oscil', 'spiral'] and type(centre) in [list, tuple]:
            c = _p3(centre)
            self.center = [c[0] * xfac, c[1] * yfac, c[2] * zfac]
            if dict.get('radius') is not None and (self.geometryTransformed or len(centre) > 2):
                self.setRadius(dict['radius'] * xfac)
            else:
                self.setRadius(self.center[0] - self.getFirstPoint()[0])
        else:
            self.center = centre
            self.radius = dict.get('radius')
        pos = dict.get('circlePos')
        self.circlePos = None if pos is None else tuple(a * b for a, b in zip(_p3(pos), (xfac, yfac, zfac)))

    def setTranspo(self, x):
        self.transpo = x
        if self.id >= 0 and self.audio is not None:
            self.audio.setTranspo(self.id, self.transpo)

    def getTranspo(self):
        return self.transpo

    def getFreeze(self):
        return self.freeze

    def setFreeze(self, freeze):
        self.freeze = freeze

    def getLabel(self):
        return self.label

    def getId(self):
        return self.id

    def getColour(self):
        return self.colour

    def getBorderColour(self):
        return self.bordercolour

    def setTimeSpeed(self, speed):
        self.timeSpeed = speed
        if self.id >= 0 and self.audio is not None:
            self.audio.setMetroTime(self.id, speed * 0.001)

    def getTimeSpeed(self):
        return self.timeSpeed

    def setAmplitude(self, val):
        self.amplitude = val

    def getAmplitude(self):
        return self.amplitude

    def setEditionLevel(self, level):
        self.editLevel = level

    def activateLp(self, state):
        self.activeLp = state

    def reinitLp(self):
        self.lpx.reinit()
        self.lpy.reinit()
        self.lpz.reinit()

    def setFilterFreq(self, freq):
        self.filterCut = freq
        self.lpx.setFreq(freq)
        self.lpy.setFreq(freq)
        self.lpz.setFreq(freq)

    def setFilterQ(self, q):
        self.lpx.setQ(q)
        self.lpy.setQ(q)
        self.lpz.setQ(q)

    def setType(self, t):
        self.type = t

    def getType(self):
        return self.type

    def setDirection(self, direction):
        self.direction = int(direction) % 3

    def getDirection(self):
        return self.direction

    def setActive(self, state=None):
        if state != None:
            self.active = state
        if self.audio is not None:
            self.audio.setActive(self.id, 1 if self.active else 0)

    def getActive(self):
        return self.active

    def _lp(self, point):
        return (self.lpx.filter(point[0]), self.lpy.filter(point[1]), self.lpz.filter(point[2]))

    def addPoint(self, point):
        point = _p3(point)
        if len(self.points) > 1:
            if point == self.points[-1]:
                return
            if self.activeLp:
                point = self._lp(point)
            self.points.append(point)
        else:
            self.points.append(point)

    def addFinalPoint(self, point, closed):
        point = _p3(point)
        if closed:
            self.points.append(point)
            first = self.points[0]
            delta = _sub(first, point)
            maxstep = int(max(abs(delta[0]), abs(delta[1]), abs(delta[2])))
            for i in range(0, maxstep, 2):
                frac = (i + 1) / float(maxstep)
                self.points.append((point[0] + delta[0] * frac,
                                    point[1] + delta[1] * frac,
                                    point[2] + delta[2] * frac))
        self.setInitPoints()

    def fillPoints(self, closed):
        fill = [BiquadLP(freq=self.filterCut) for i in range(3)]

        def lp(p):
            return tuple(f.filter(v) for f, v in zip(fill, p))

        templist = []
        if closed:
            length = len(self.points)
        else:
            length = len(self.points) - 1
        for i in range(length):
            if closed:
                first = i - 1
                second = i
            else:
                first = i
                second = i + 1
            a, b = self.points[first], self.points[second]
            step = _length(_sub(a, b))
            p = lp(a) if self.activeLp else tuple(a)
            if not templist or p != templist[-1]:
                templist.append(p)
            if step > 3:
                mid = ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5, (a[2] + b[2]) * 0.5)
                p = lp(mid) if self.activeLp else mid
                if p != templist[-1]:
                    templist.append(p)
        templist.append(lp(self.points[-1]))
        templist.append(tuple(self.points[-1]))
        if self.sphere:
            # a shape drawn on a sphere stays on it: the points put in between go back out to it
            templist = [onSphere(p, self.sphere) for p in templist]
        self.points = [(p[0], p[1], p[2]) for p in templist]

    def setInitPoints(self):
        self.initPoints = [(p[0], p[1], p[2]) for p in self.points]

    def editTraj(self, index, offset):
        """Pull the clicked point by offset (subtracted, as in SoundGrain) and its
        neighbours with it, less and less with distance along the path."""
        offset = _p3(offset)
        count = len(self.initPoints)
        p_off = int(count / self.editLevel)
        # clicked point
        self.points[index] = tuple(self.initPoints[index][k] - offset[k] for k in range(3))
        for i in range(1, p_off):
            # sigmoid scaling function
            off = (p_off - i) / float(p_off) * 0.5
            mult = .5 + (sin((off + .75) * 2 * pi) * .5)
            # scales i points each side of clicked point
            iplus = index + i if index + i < count else index + i - count
            for j in (index - i, iplus):
                self.points[j] = tuple(self.initPoints[j][k] - offset[k] * mult for k in range(3))

    def move(self, offset):
        offset = _p3(offset)
        self.points = [(p[0] - offset[0], p[1] - offset[1], p[2] - offset[2]) for p in self.initPoints]
        if self.getFreeze() and self.circlePos is not None:
            self.circlePos = tuple(self.circlePos[k] - offset[k] for k in range(3))

    def getFirstPoint(self):
        if self.points == []:
            return None
        else:
            return self.points[0]

    def setPointPos(self, point):
        self.circlePos = point

    def getPoints(self):
        return self.points

    def setPoints(self, plist, xfac=1.0, yfac=1.0, zfac=1.0):
        if not plist:
            self.clear()
        else:
            self.points = [(p[0] * xfac, p[1] * yfac, (p[2] if len(p) > 2 else 0.0) * zfac) for p in plist]
            self.setInitPoints()

    def getPointPos(self):
        return self.circlePos

    def setStep(self, step):
        self.step = step

    def getStep(self):
        return self.step

    def initCounter(self):
        self.counter = 0
        self.resetWander()

    def currentIndex(self):
        """Which point the counter is at, for the playback direction."""
        count = len(self.points)
        if count == 0:
            return 0
        if self.direction == 1:
            return (count - 1) - (self.counter % count)
        if self.direction == 2 and count > 1:
            period = 2 * (count - 1)
            c = self.counter % period
            return c if c < count else period - c
        return self.counter % count

    def getPhase(self):
        """How far along the path the playback point is, 0..1."""
        count = len(self.points)
        if count < 2:
            return 0.0
        return (self.lastIndex % count) / float(count - 1)

    def clock(self):
        if not self.freeze:
            if self.points:
                if self.circlePos != None:
                    self.lastCirclePos = self.circlePos
                self.lastIndex = self.currentIndex()
                self.circlePos = self._displacedPoint(self.lastIndex)
                self.counter += self.step
                self.mario = (self.mario + 1) % 4

    ### Circle functions ###
    def addCirclePoint(self, point):
        point = _p3(point)
        if len(self.points) > 1:
            if point == self.points[-1]:
                return
            if self.activeLp:
                point = self._lp(point)
        self.points.append(point)

    def getLosangePoint(self):
        return self.points[int(len(self.points) * 2 / 3)]

    def getCenter(self):
        if self.center is None:
            return None
        else:
            return tuple(self.center)

    def setCenter(self, c):
        self.center = None if c is None else list(_p3(c))

    def getRadius(self):
        if self.radius is None:
            return None
        else:
            return self.radius

    def setRadius(self, r):
        self.radius = r

    def setBasis(self, u, v, w=None):
        """The plane of a circle, oscil or spiral: u and v span it, w is its normal."""
        if w is None:
            w = _cross(u, v)
        self.basis = [tuple(float(a) for a in u), tuple(float(a) for a in v), tuple(float(a) for a in w)]

    def getBasis(self):
        if self.basis is None:
            return [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
        return self.basis

    # ------------------------------------------------------------------
    # shapes: the points of a circle, an oscillation or a spiral
    # ------------------------------------------------------------------
    def buildShape(self, oscilPeriod=2, oscilScaling=1, clip=None):
        """(Re)make the points of a circle / oscil / spiral from centre, radius and plane.

        Same point counts and angles as SoundGrain's, so a shape of a given
        radius plays at the same speed; the spiral climbs along the plane's
        normal, oscilPeriod turns over a height of oscilScaling radii.
        """
        r = float(self.radius or 0)
        c = self.getCenter()
        u, v, w = self.getBasis()
        halfR = int(round(r / 2.))
        scaleR = 1 if halfR <= 1 else 1. / (halfR - 1)
        self.points = []
        self.reinitLp()
        kind = self.getType()
        if kind == 'circle':
            indices = range(-halfR, halfR + 1)
        elif kind == 'oscil':
            indices = range(int(-halfR * oscilScaling), int(halfR * oscilScaling + 1))
        else:
            turns = max(0.25, float(oscilPeriod))
            indices = range(int(-halfR * turns), int(halfR * turns + 1))
        indices = list(indices)
        for n, i in enumerate(indices):
            a = cos(pi * i * scaleR) * r
            if kind == 'circle':
                b, h = sin(pi * i * scaleR) * r, 0.0
            elif kind == 'oscil':
                b, h = sin(pi * oscilPeriod * i * scaleR) * r, 0.0
            else:
                b = sin(pi * i * scaleR) * r
                frac = n / float(max(1, len(indices) - 1))
                h = (frac - 0.5) * 2.0 * r * oscilScaling
            p = tuple(c[k] + u[k] * a + v[k] * b + w[k] * h for k in range(3))
            if self.sphere:
                p = onSphere(p, self.sphere)
            if clip is not None:
                p = clip(p)
            self.addCirclePoint(p)
