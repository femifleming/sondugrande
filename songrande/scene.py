"""
Songrande - the scene: sixteen trajectories and the FX balls, in a room.

Everything SoundGrain's drawing surface knew that is not a pixel lives here:
making trajectories (free-hand, circle, oscillation, line, spiral), editing,
moving and transforming them, the memorised trajectory MIDI notes play, and
the clock that walks along them and tells the sound engine where each stream
is. There is no GUI in this file: the 3D surface turns the pointer into points
of the room and calls these methods, and so do the tests, the self-test and
the offline renderer.

Copyright 2009-2017 Olivier Belanger (SoundGrain), Songrande additions 2026.
This file is part of Songrande, a derivative of SoundGrain, released under the
GNU General Public License version 3 or later.
"""
import math

from .constants import MAX_STREAMS, TRAJTYPES, SHAPES
from .Trajectory import Trajectory, _p3, _sub, _length, _cross
from . import space


class Ball:
    """An FX ball: a sphere of the room that sends the streams inside it to an
    effect, whose sound comes out from the ball's centre."""

    def __init__(self, fx, id, center=(500.0, 250.0, 0.0), size=128.0, gradient=30, fader=1.0):
        self.fx = fx
        self.id = id
        self._center = self.center = tuple(_p3(center))
        self.size = float(size)
        self.halfSize = self.size / 2.0
        self._gradient = self.gradient = gradient
        self.fader = fader
        # SoundGrain's four sliders; the fourth, its pan, is the spread of the ball's sound
        self.sliders = {"slider1": None, "slider2": None, "slider3": 1.0, "slider4": 0.25}
        self.gui = None

    def getFx(self):
        return self.fx

    def getId(self):
        return self.id

    def getCenter(self):
        return self.center

    def setCenter(self, c):
        self._center = self.center = tuple(_p3(c))

    def restoreCenter(self):
        self.center = self._center

    def restoreGradient(self):
        self.gradient = self._gradient

    def getSize(self):
        return self.size

    def setSize(self, size):
        self.size = max(8.0, float(size))
        self.halfSize = self.size / 2.0

    def resize(self, size):
        self.setSize(size)

    def move(self, newpos):
        self._center = self.center = space.clip_canvas(_p3(newpos))

    def setGradient(self, x):
        """SoundGrain's shift-drag: how fast the send falls off towards the edge."""
        self._gradient = min(255, max(30, self.gradient + x))
        self.fader = 1. - ((self._gradient - 30) / 225.)

    def getAmpValue(self, pos):
        if pos is None:
            return 0.0
        hyp = _length(_sub(self.center, _p3(pos)))
        if hyp < self.halfSize:
            return pow((self.halfSize - (hyp * self.fader)) / self.halfSize, 2)
        return 0.0

    def save(self):
        return {"fx": self.fx, "id": self.id, "center": list(self.center), "size": self.size,
                "gradient": self.gradient, "fader": self.fader, "controls": dict(self.sliders)}


class Scene:
    def __init__(self, audio=None):
        self.audio = audio
        self.trajectories = [Trajectory(self, i + 1) for i in range(MAX_STREAMS)]
        self.memorizedTrajectory = Trajectory(self, -1)
        self.memorizedId = {}
        self.midiTranspose = True
        self.midiXposition = 0
        self.midiOctaveSpread = 2
        self.fxballs = {}
        self.selected = self.trajectories[0]
        self.closed = 0
        self.oscilPeriod = 2
        self.oscilScaling = 1
        self.mode = TRAJTYPES[0]
        self.lowpass = True
        self.fillPoints = True
        self.editionLevel = 2
        self.penWidth = 2
        self.wanderSpeed = 1.0
        self.wanderPeriodicity = 0.0
        self.xSource = 0
        self.ySource = 0
        self.flock = 0.0           # 0: every ball stays on its line; 1: they fly as a flock
        self.boids = {}            # stream -> [position, velocity] of its ball when flocking
        self.traj = None

    # ------------------------------------------------------------------
    # the clock: called by the sound engine, once per timer tick of a stream
    # ------------------------------------------------------------------
    def flockPosition(self, t, target):
        """Where a stream sounds when the balls flock (after the boids of openfield).

        Each ball is a bird on a leash to its own trajectory's point: it is
        pulled towards that point, towards the middle of the others and along
        with them, and pushed away from any that come too near. 'flock' is how
        much of this flight is heard: at 0 the ball is on its line.
        """
        if self.flock <= 0.0:
            self.boids.pop(t.getId(), None)
            t.soundPos = None
            return target
        dt = min(0.1, max(0.001, t.getTimeSpeed() * 0.001))
        boid = self.boids.get(t.getId())
        if boid is None:
            boid = self.boids[t.getId()] = [list(target), [0.0, 0.0, 0.0]]
        p, v = boid
        others = [self.boids[i] for i in list(self.boids) if i != t.getId() and self.trajectories[i].getActive()]
        acc = [(target[k] - p[k]) * 6.0 - v[k] * 2.2 for k in range(3)]        # the leash, and the air
        if others:
            n = float(len(others))
            for k in range(3):
                centre = sum(o[0][k] for o in others) / n
                heading = sum(o[1][k] for o in others) / n
                acc[k] += (centre - p[k]) * 2.0 + (heading - v[k]) * 0.8       # together, and the same way
            for o in others:
                gap = _sub(p, o[0])
                dist = _length(gap)
                if 1e-6 < dist < 90.0:
                    push = (90.0 - dist) / dist * 12.0
                    for k in range(3):
                        acc[k] += gap[k] * push                                # not too close
        for k in range(3):
            v[k] += acc[k] * dt
            p[k] += v[k] * dt
        clipped = space.clip_canvas(p)
        for k in range(3):
            if clipped[k] != p[k]:
                p[k], v[k] = clipped[k], 0.0
        out = space.clip_canvas(tuple(target[k] + (p[k] - target[k]) * self.flock for k in range(3)))
        t.soundPos = out
        return out

    def clock(self, which):
        t = self.trajectories[which]
        t.clock()
        if t.getActive() and self.audio is not None:
            pos = t.getPointPos()
            if pos is not None:
                pos = self.flockPosition(t, pos)
                x, y = space.grain_xy(pos, t.getPhase(), self.xSource, self.ySource)
                # Y first: the place in the sound takes the grains' pitch and length into account
                self.audio.setYposition(which, y)
                self.audio.setXposition(which, x)
                self.audio.setSpatial(which, pos)
                for ball in list(self.fxballs.values()):
                    self.audio.setMixerChannelAmp(which, ball.getId(), ball.getAmpValue(pos))

    def getValues(self):
        vals = []
        for t in self.trajectories:
            if t.getPointPos() != None:
                vals.append(list(space.grain_xy(t.getPointPos(), t.getPhase(), self.xSource, self.ySource)))
            else:
                vals.append([])
        return vals

    # ------------------------------------------------------------------
    def setMode(self, mode):
        self.mode = TRAJTYPES[mode] if not isinstance(mode, str) else mode

    def setClosed(self, closed):
        self.closed = closed

    def setOscilPeriod(self, period):
        self.oscilPeriod = period

    def getOscilPeriod(self):
        return self.oscilPeriod

    def setOscilScaling(self, scaling):
        self.oscilScaling = scaling

    def getOscilScaling(self):
        return self.oscilScaling

    def setMidiTranspose(self, value):
        self.midiTranspose = value

    def setMidiXposition(self, value):
        self.midiXposition = value

    def setMidiOctaveSpread(self, value):
        self.midiOctaveSpread = value

    def getTrajectory(self, which):
        return self.trajectories[which]

    def getAllTrajectories(self):
        return self.trajectories

    def getActiveTrajectories(self):
        return [t for t in self.trajectories if t.getActive()]

    def resetTrajectories(self):
        self.trajectories = [Trajectory(self, i + 1) for i in range(MAX_STREAMS)]
        self.memorizedTrajectory = Trajectory(self, -1)
        self.memorizedId = {}
        self.selected = self.trajectories[0]

    def setSelectedById(self, id):
        self.selected = self.trajectories[id]

    def firstFree(self):
        for t in self.trajectories:
            if not t.getActive():
                return t
        return None

    def clearTrajectory(self, t):
        t.clear()
        active = self.getActiveTrajectories()
        self.selected = active[0] if active else self.trajectories[0]
        return self.selected

    # ------------------------------------------------------------------
    # drawing a new trajectory (the surface feeds points of the room)
    # ------------------------------------------------------------------
    def _prepare(self, t, kind):
        t.setWidth(self.penWidth)
        t.setWanderSpeed(self.wanderSpeed)
        t.setWanderPeriodicity(self.wanderPeriodicity)
        t.resetWander()
        t.geometryTransformed = False
        t.closed = kind == 'circle' or (kind == 'free' and bool(self.closed))
        t.setActive(True)
        t.setType(kind)
        t.reinitLp()
        t.activateLp(self.lowpass)
        t.setEditionLevel(self.editionLevel)

    def beginDraw(self, point, basis=None, sphere=None):
        """Pen down at a point of the room. basis: the plane (u, v, normal) a
        circle, oscillation or spiral lies in; the floor if not given. sphere:
        the radius of the sphere a shape is wrapped on, if it is drawn on one."""
        self.traj = t = self.firstFree()
        if t is None:
            return None
        point = space.clip_canvas(_p3(point))
        self.downPos = point
        self._prepare(t, self.mode)
        if t.getType() == 'free':
            t.addPoint(point)
        elif t.getType() in SHAPES:
            t.setCenter(point)
            t.setRadius(0)
            if basis is None:
                basis = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
            t.setBasis(*basis)
            t.sphere = sphere
        return t

    def drawTo(self, point):
        """Pen moved to a point of the room."""
        t = self.traj
        if t is None:
            return
        point = space.clip_canvas(_p3(point))
        kind = t.getType()
        if kind == 'free':
            t.addPoint(point)
        elif kind == 'line':
            t.points = []
            t.reinitLp()
            delta = _sub(point, self.downPos)
            maxstep = int(_length(delta))
            for i in range(0, maxstep, 2):
                frac = i / float(maxstep)
                t.addPoint(tuple(self.downPos[k] + delta[k] * frac for k in range(3)))
        else:
            radius = _length(_sub(point, t.getCenter()))
            t.setRadius(self.clipRadius(radius, t.getCenter(), t.getBasis()))
            t.buildShape(self.oscilPeriod, self.oscilScaling, space.clip_canvas)

    def endDraw(self, point=None):
        """Pen up. Returns the new trajectory, or None if nothing was drawn."""
        t = self.traj
        self.traj = None
        if t is None:
            return None
        if len(t.getPoints()) <= 1:
            t.clear()
            return None
        if t.getType() == 'free':
            if point is None:
                point = t.getPoints()[-1]
            t.addFinalPoint(space.clip_canvas(_p3(point)), t.closed)
            if self.fillPoints:
                t.fillPoints(t.closed)
            t.setInitPoints()
        else:
            if self.fillPoints:
                t.fillPoints(False)
            t.setInitPoints()
        self.selected = t
        return t

    def clipRadius(self, radius, center, basis):
        """The largest radius that keeps a shape inside the room."""
        u, v, w = basis
        limits = ((0.0, space.CANVAS), (0.0, space.CANVAS), (-space.HEIGHT, space.HEIGHT))
        best = radius
        for k in range(3):
            reach = math.sqrt(u[k] * u[k] + v[k] * v[k])
            if reach < 1e-9:
                continue
            low, high = limits[k]
            room = min(center[k] - low, high - center[k])
            best = min(best, max(0.0, room) / reach)
        return max(0.0, best)

    def addTrajectory(self, kind, points=None, center=None, radius=None, basis=None, closed=None,
                      sphere=None):
        """Make a trajectory at once, from points or from a centre and a radius.
        Used by scripts, the self-test and the tests."""
        t = self.firstFree()
        if t is None:
            return None
        self._prepare(t, kind)
        if closed is not None:
            t.closed = bool(closed)
        if kind in SHAPES:
            t.setCenter(center)
            t.setBasis(*(basis or ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))))
            t.sphere = sphere
            t.setRadius(self.clipRadius(radius, t.getCenter(), t.getBasis()))
            t.buildShape(self.oscilPeriod, self.oscilScaling, space.clip_canvas)
            if self.fillPoints:
                t.fillPoints(False)
        else:
            was, t.activeLp = t.activeLp, False
            for p in points:
                t.addPoint(space.clip_canvas(_p3(p)))
            t.activeLp = was
            if kind == 'free' and t.closed:
                t.addFinalPoint(t.getPoints()[-1], True)
        t.setInitPoints()
        self.selected = t
        return t

    # ------------------------------------------------------------------
    # moving, editing, rescaling
    # ------------------------------------------------------------------
    def clipOffset(self, t, offset):
        """Limit a move (offset is subtracted from the points) to the room."""
        pts = t.initPoints or t.points
        if not pts:
            return offset
        out = []
        limits = ((0.0, space.CANVAS), (0.0, space.CANVAS), (-space.HEIGHT, space.HEIGHT))
        for k in range(3):
            low = min(p[k] for p in pts)
            high = max(p[k] for p in pts)
            lo_lim, hi_lim = limits[k]
            off = offset[k]
            off = min(off, low - lo_lim)       # moving down / left by off
            off = max(off, high - hi_lim)
            out.append(off)
        return tuple(out)

    def moveTrajectory(self, t, offset, centre=None):
        """Move by (start - now); centre is where the shape's centre was at the start."""
        offset = self.clipOffset(t, _p3(offset))
        if any(abs(v) > 1e-9 for v in offset):
            t.sphere = None        # it has left the sphere it was drawn on
        t.move(offset)
        if t.getType() in SHAPES and centre is not None:
            t.setCenter(tuple(centre[k] - offset[k] for k in range(3)))
        return offset

    def rescaleShape(self, t, radius):
        t.setRadius(self.clipRadius(radius, t.getCenter(), t.getBasis()))
        if t.geometryTransformed and getattr(t, "rescaleRadius", None):
            c = t.getCenter()
            factor = t.getRadius() / t.rescaleRadius
            t.points = [tuple(c[k] + (p[k] - c[k]) * factor for k in range(3)) for p in t.initPoints]
        else:
            t.buildShape(self.oscilPeriod, self.oscilScaling, space.clip_canvas)

    def endRescale(self, t):
        if not t.geometryTransformed and self.fillPoints:
            t.fillPoints(t.getType() == 'circle')
        t.setInitPoints()

    def endEdit(self, t):
        t.sphere = None
        if self.fillPoints:
            t.fillPoints(False)
        t.setInitPoints()
        t.setType('free')

    def duplicateTrajectory(self, source):
        """Copy a trajectory into the first available slot and select it."""
        target = self.firstFree()
        if target is None:
            return None
        target.setActive(True)
        target.setType(source.getType())
        target.reinitLp()
        target.activateLp(self.lowpass)
        target.setEditionLevel(self.editionLevel)
        target.setWidth(source.getWidth())
        target.setWanderSpeed(source.getWanderSpeed())
        target.setWanderPeriodicity(source.getWanderPeriodicity())
        target.setTimeSpeed(source.getTimeSpeed())
        target.setStep(source.getStep())
        target.setDirection(source.getDirection())
        target.closed = source.closed
        target.geometryTransformed = source.geometryTransformed
        target.setPoints(source.getPoints())
        if target.getType() in SHAPES:
            target.setRadius(source.getRadius())
            target.setCenter(source.getCenter())
            target.setBasis(*source.getBasis())
            target.sphere = source.sphere
        self.selected = target
        return target

    # ------------------------------------------------------------------
    # transformations of the selected trajectory
    # ------------------------------------------------------------------
    def transform(self, t, operation, amount=0.0):
        """Flip, turn, tilt, lift, scale or wrap a trajectory.

        operation: 'horizontal' (left - right flip), 'vertical' (front - back
        flip), 'updown' (height flip), 'rotate' (about the vertical, degrees),
        'tiltx' (about the left - right axis), 'tilty' (about the front - back
        axis), 'lift' (canvas units up), 'scale' (factor), 'sphere' (onto the
        sphere of that radius, in radii), 'flatten' (to its mean height).
        """
        if t is None or not t.getActive() or len(t.points) < 2:
            return False
        pts = t.points
        xs, ys, zs = zip(*pts)
        if operation in ('rotate', 'tiltx', 'tilty', 'scale') and t.getType() in SHAPES and t.center is not None:
            c = tuple(t.center)
        elif operation in ('rotate', 'tiltx', 'tilty', 'scale'):
            c = (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))
        else:
            c = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, (min(zs) + max(zs)) / 2.0)
        rad = math.radians(amount)
        cosine, sine = math.cos(rad), math.sin(rad)
        mean_z = sum(zs) / len(zs)

        def vector(d):
            dx, dy, dz = d
            if operation == 'horizontal':
                return (-dx, dy, dz)
            if operation == 'vertical':
                return (dx, -dy, dz)
            if operation == 'updown':
                return (dx, dy, -dz)
            if operation == 'rotate':
                return (cosine * dx - sine * dy, sine * dx + cosine * dy, dz)
            if operation == 'tiltx':      # canvas y runs to the back, so this raises the front for a positive angle
                return (dx, cosine * dy + sine * dz, -sine * dy + cosine * dz)
            if operation == 'tilty':
                return (cosine * dx - sine * dz, dy, sine * dx + cosine * dz)
            if operation == 'scale':
                return (dx * amount, dy * amount, dz * amount)
            return (dx, dy, dz)

        def point(p):
            if operation == 'lift':
                return (p[0], p[1], p[2] + amount)
            if operation == 'flatten':
                return (p[0], p[1], mean_z)
            if operation == 'sphere':
                room = ((p[0] - space.HALF), (space.HALF - p[1]), p[2])
                length = math.sqrt(sum(a * a for a in room))
                if length < 1e-6:
                    return p
                k = amount * space.HALF / length
                return (room[0] * k + space.HALF, space.HALF - room[1] * k, room[2] * k)
            d = vector(_sub(p, c))
            return (c[0] + d[0], c[1] + d[1], c[2] + d[2])

        new = [space.clip_canvas(point(p)) for p in pts]
        t.points = new
        if t.center is not None and len(t.center) == 3:
            t.center = list(space.clip_canvas(point(tuple(t.center))))
        if t.circlePos is not None:
            t.circlePos = space.clip_canvas(point(_p3(t.circlePos)))
        if t.lastCirclePos is not None:
            t.lastCirclePos = space.clip_canvas(point(_p3(t.lastCirclePos)))
        if t._normal is not None and operation in ('horizontal', 'vertical', 'rotate'):
            t._normal = vector(t._normal)
        if t.basis is not None and operation not in ('lift', 'flatten', 'sphere', 'scale'):
            t.basis = [vector(b) for b in t.basis]
        if operation == 'scale' and t.radius:
            t.radius = t.radius * amount
        if operation == 'sphere' and t.getType() in SHAPES:
            t.sphere = amount
        else:
            t.sphere = None        # it has left the sphere it was drawn on
        if t.getType() in SHAPES:
            t.geometryTransformed = True
        t.setInitPoints()
        return True

    # ------------------------------------------------------------------
    # the memorised trajectory (MIDI)
    # ------------------------------------------------------------------
    def memorize(self):
        t = self.selected
        m = self.memorizedTrajectory
        m.setWidth(t.getWidth())
        m.setWanderSpeed(t.getWanderSpeed())
        m.setWanderPeriodicity(t.getWanderPeriodicity())
        m.closed = t.closed
        m.geometryTransformed = t.geometryTransformed
        m.setType(t.getType())
        m.setTimeSpeed(t.getTimeSpeed())
        m.setStep(t.getStep())
        m.setDirection(t.getDirection())
        m.activateLp(self.lowpass)
        m.setEditionLevel(self.editionLevel)
        m.setPoints(t.getPoints())
        m.setInitPoints()
        if m.getType() in SHAPES:
            m.setRadius(t.getRadius())
            m.setCenter(t.getCenter())
            m.setBasis(*t.getBasis())
            m.sphere = t.sphere
        if self.midiXposition and m.getFirstPoint() is not None:
            off = (space.CANVAS / 2) - m.getFirstPoint()[0]
            m.move((-off, 0, 0))
            m.setInitPoints()

    def addTrajFromMemory(self, index, pitch, normy, midinote):
        t = self.memorizedTrajectory
        if not t.getPoints():
            return None
        new_t = self.firstFree()
        if new_t is None:
            return None
        self.memorizedId[index] = new_t.getId()
        new_t.setTimeSpeed(t.getTimeSpeed())
        new_t.setTranspo(pitch if self.midiTranspose else 1.0)
        new_t.setWidth(t.getWidth())
        new_t.setWanderSpeed(t.getWanderSpeed())
        new_t.setWanderPeriodicity(t.getWanderPeriodicity())
        new_t.closed = t.closed
        new_t.geometryTransformed = t.geometryTransformed
        new_t.setStep(t.getStep())
        new_t.setDirection(t.getDirection())
        new_t.setActive(True)
        new_t.setType(t.getType())
        new_t.reinitLp()
        new_t.activateLp(self.lowpass)
        new_t.setEditionLevel(self.editionLevel)
        new_t.setPoints(t.getPoints())
        new_t.setInitPoints()
        if new_t.getType() in SHAPES:
            new_t.setCenter(t.getCenter())
            new_t.setRadius(t.getRadius())
            new_t.setBasis(*t.getBasis())
            new_t.sphere = t.sphere
        downPos = new_t.getFirstPoint()
        w = h = space.CANVAS
        if not self.midiXposition:
            x, y = downPos[0], (1. - normy) * h
        else:
            x = (w / 2) + (w * (midinote - 60) / 12. / self.midiOctaveSpread)
            y = (1. - normy) * h
        centre = new_t.getCenter()
        self.moveTrajectory(new_t, (downPos[0] - x, downPos[1] - y, 0.0), centre)
        new_t.setInitPoints()
        return new_t

    def deleteMemorizedTraj(self, index):
        if index not in self.memorizedId:
            return
        t = self.trajectories[self.memorizedId.pop(index)]
        self.clearTrajectory(t)

    # ------------------------------------------------------------------
    # FX balls
    # ------------------------------------------------------------------
    def addFxBall(self, fx, center=None, size=128.0):
        key = -1
        for i in range(10):
            if i not in self.fxballs:
                key = i
                break
        if key == -1:
            return None
        if center is None:
            center = (space.HALF * 0.3 + 60 * key, space.HALF * 0.3, 0.0)
        ball = Ball(fx, key, center, size)
        self.fxballs[key] = ball
        if self.audio is not None:
            self.audio.addFx(fx, key)
            self.audio.placeFx(key, ball.getCenter(), ball.sliders["slider4"])
        return ball

    def restoreFxBall(self, d, xfac=1.0, yfac=1.0):
        if "center" in d:
            center, size = d["center"], d["size"]
        else:
            # a SoundGrain ball: pos was its top-left corner in window pixels
            size = d["size"] * (xfac + yfac) * 0.5
            center = (d["pos"][0] * xfac + size / 2.0, d["pos"][1] * yfac + size / 2.0, 0.0)
        ball = Ball(d["fx"], d["id"], center, size, d.get("gradient", 30), d.get("fader", 1.0))
        controls = d.get("controls") or {}
        for name in ball.sliders:
            if name in controls and controls[name] is not None:
                ball.sliders[name] = controls[name]
        if "pos" in d and "center" not in d:
            ball.sliders["slider4"] = 0.25
        self.fxballs[ball.id] = ball
        if self.audio is not None:
            self.audio.addFx(ball.fx, ball.id)
            self.applyBallSliders(ball)
        return ball

    def applyBallSliders(self, ball):
        """Send a ball's slider values and place to the sound engine."""
        a = self.audio
        if a is None or ball.id not in a.fxs:
            return
        s = ball.sliders
        if s["slider1"] is not None:
            a.handleFxSlider1(ball.fx, ball.id, s["slider1"])
        if s["slider2"] is not None:
            a.handleFxSlider2(ball.fx, ball.id, s["slider2"])
        a.handleFxMul(ball.id, s["slider3"])
        a.placeFx(ball.id, ball.getCenter(), s["slider4"])

    def placeBall(self, ball):
        if self.audio is not None:
            self.audio.placeFx(ball.id, ball.getCenter(), ball.sliders["slider4"])

    def removeFxBall(self, key):
        if key in self.fxballs:
            del self.fxballs[key]
            if self.audio is not None:
                self.audio.removeFx(key)

    def removeAllFxBalls(self):
        for key in list(self.fxballs.keys()):
            self.removeFxBall(key)

    # ------------------------------------------------------------------
    # saving and loading
    # ------------------------------------------------------------------
    def getState(self):
        return {
            "Trajectories": {str(i): t.getAttributes() for i, t in enumerate(self.trajectories)},
            "MemorizedTrajectory": self.memorizedTrajectory.getAttributes(),
            "fxballs": {str(key): ball.save() for key, ball in self.fxballs.items()},
        }

    def setTrajectories(self, d, xfac=1.0, yfac=1.0):
        for i, t in enumerate(self.trajectories):
            if str(i) in d["Trajectories"]:
                t.setAttributes(d["Trajectories"][str(i)], xfac, yfac)
        if 'MemorizedTrajectory' in d:
            self.memorizedTrajectory.setAttributes(d['MemorizedTrajectory'], xfac, yfac)

    def setFxBalls(self, d, xfac=1.0, yfac=1.0):
        for ball in d.values():
            self.restoreFxBall(ball, xfac, yfac)


def legacyFactors(state):
    """Scale factors that lay a SoundGrain project's window on the floor of the room."""
    if "Space" in state:
        return 1.0, 1.0
    size = state.get("SurfaceSize") or state.get("MainFrame", {}).get("size")
    if not size:
        return 1.0, 1.0
    return space.CANVAS / float(size[0]), space.CANVAS / float(size[1])
