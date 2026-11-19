"""
Copyright 2009-2017 Olivier Belanger (SoundGrain's DrawingSurface)
Songrande: the drawing surface as a room.

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

SoundGrain's surface, the sound's waveform with trajectories drawn over it, is
the floor of a room here, seen from any side, and the pen can leave it:

* draw on the Floor (a level plane at the pen's height), on the Sphere (the
  loudspeaker sphere, or one of another radius) or on the View plane (the
  plane facing you);
* hold Cmd (Ctrl on Windows and Linux) while drawing or dragging, or turn the
  wheel, to pull the pen straight up or down (in or out on the sphere);
* right-drag or Alt-drag empty space to walk round the room, turn the wheel
  to come closer, and use the Top, Front and Side views to place things
  exactly.

Everything else is SoundGrain's: the red square moves a trajectory, the blue
one resizes a circle, any other point of a line pulls it, the FX balls are
dragged by their middle and resized by their rim.
"""
import wx, os, math, sys
import numpy as np
from .constants import *
from .FxBall import FxBallControls, BallPicture
from .scene import Scene
from .Trajectory import Trajectory
from . import space


def cv(room_vec):
    """A room direction (right, front, up) as a canvas direction."""
    return (float(room_vec[0]), -float(room_vec[1]), float(room_vec[2]))


def rv(canvas_vec):
    """A canvas direction as a room direction."""
    return np.array([canvas_vec[0], -canvas_vec[1], canvas_vec[2]], dtype=float)


class MyFileDropTarget(wx.FileDropTarget):
    def __init__(self, window):
        wx.FileDropTarget.__init__(self)
        self.window = window

    def OnDropFiles(self, x, y, filenames):
        for file in filenames:
            ext = os.path.splitext(file)[1].replace(".", "")
            if ext.lower() in ("sg", PROJECT_EXT):
                self.window.GetTopLevelParent().loadFile(ensureNFD(file))
            elif ext.lower() in ALLOWED_EXTENSIONS:
                self.window.GetTopLevelParent().controls.loadSound(ensureNFD(file))
        return True


class Surface3D(wx.Panel):
    def __init__(self, parent, pos=(0,0), size=wx.DefaultSize):
        wx.Panel.__init__(self, parent=parent, id=wx.ID_ANY, pos=pos, size=size, style = wx.EXPAND | wx.WANTS_CHARS)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.parent = parent
        dt = MyFileDropTarget(self)
        self.SetDropTarget(dt)
        self.scene = Scene()
        self.camera = space.Camera()
        self.drawOn = 0            # index in DRAW_SURFACES
        self.penHeight = 0.0       # height of the floor plane the pen draws on, in radii
        self.sphereRadius = 1.0    # radius of the sphere the pen draws on, in radii
        self.useMario = False
        self.needBitmap = True     # kept for SoundGrain's callers: the room is redrawn at every paint
        self.onMotion = False
        self.marios = [wx.Bitmap(os.path.join(IMAGES_PATH, 'Mario%d.png' % i), wx.BITMAP_TYPE_PNG) for i in [1,2,3,2,4,5,6,5]]
        if PLATFORM == "darwin":
            fontsize = 10
        else:
            fontsize = 8
        self.font = wx.Font(fontsize, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.font_pos = wx.Font(fontsize, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.pictures = {}
        self.sndBitmap = None      # SoundGrain's flag "a waveform is shown"
        self.list = []
        self.waveform = []
        self.bitmapDict = {}
        self.zoomWaveform = None
        self.pointerPos = None     # screen
        self.hover = None          # room point under the pointer
        self.action = None
        self.traj = None
        self.fxball = None
        self.buttons = []
        self.pen = None            # room point being dragged
        self.penKind = 'floor'
        self.penRadius = 1.0
        self.lastMouse = (0, 0)
        self.SetColors(outline=(255,255,255), bg=(30,30,30), fill=(184,32,32), rect=(0,255,0), losa=(0,0,255), wave=(70,70,70))

        self.Bind(wx.EVT_KEY_DOWN, self.KeyDown)
        self.Bind(wx.EVT_KEY_UP, self.KeyUp)
        self.Bind(wx.EVT_LEFT_DOWN, self.MouseDown)
        self.Bind(wx.EVT_LEFT_DCLICK, self.MouseDoubleClick)
        self.Bind(wx.EVT_LEFT_UP, self.MouseUp)
        self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
        self.Bind(wx.EVT_RIGHT_UP, self.OnRightUp)
        self.Bind(wx.EVT_MIDDLE_DOWN, self.OnMiddleDown)
        self.Bind(wx.EVT_MIDDLE_UP, self.OnRightUp)
        self.Bind(wx.EVT_MOTION, self.MouseMotion)
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_SIZE, self.OnResize)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeave)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self.OnCaptureLost)

        if sys.platform == "win32":
            self.dcref = wx.BufferedPaintDC
        else:
            self.dcref = wx.PaintDC

    # ------------------------------------------------------------------
    # SoundGrain's surface, as the rest of the application knows it
    # ------------------------------------------------------------------
    trajectories = property(lambda self: self.scene.trajectories)
    memorizedTrajectory = property(lambda self: self.scene.memorizedTrajectory)
    memorizedId = property(lambda self: self.scene.memorizedId)
    fxballs = property(lambda self: self.scene.fxballs)
    selected = property(lambda self: self.scene.selected)
    mode = property(lambda self: self.scene.mode)

    def setAudio(self, audio):
        self.scene.audio = audio

    def clock(self, which):
        self.scene.clock(which)

    def getValues(self):
        return self.scene.getValues()

    def setMidiTranspose(self, value):
        self.scene.setMidiTranspose(value)

    def setMidiXposition(self, value):
        self.scene.setMidiXposition(value)

    def setMidiOctaveSpread(self, value):
        self.scene.setMidiOctaveSpread(value)

    def setOscilPeriod(self, period):
        self.scene.setOscilPeriod(period)

    def getOscilPeriod(self):
        return self.scene.getOscilPeriod()

    def setOscilScaling(self, scaling):
        self.scene.setOscilScaling(scaling)

    def getOscilScaling(self):
        return self.scene.getOscilScaling()

    def setMode(self, mode):
        self.scene.setMode(mode)

    def setClosed(self, closed):
        self.scene.setClosed(closed)

    def getTrajectory(self, which):
        return self.scene.getTrajectory(which)

    def getAllTrajectories(self):
        return self.scene.getAllTrajectories()

    def getActiveTrajectories(self):
        return self.scene.getActiveTrajectories()

    def resetTrajectories(self):
        self.scene.resetTrajectories()

    def setSelectedById(self, id):
        self.scene.setSelectedById(id)

    def setSelected(self, traj):
        self.scene.selected = traj
        self.parent.controls.setSelected(traj.getId())

    def Memorize(self):
        self.syncScene()
        self.scene.memorize()

    def addTrajFromMemory(self, index, pitch, normy, midinote):
        self.syncScene()
        self.scene.addTrajFromMemory(index, pitch, normy, midinote)
        wx.CallAfter(self.Refresh)

    def deleteMemorizedTraj(self, index):
        self.scene.deleteMemorizedTraj(index)
        wx.CallAfter(self.afterDelete)

    def afterDelete(self):
        self.parent.controls.setSelected(self.scene.selected.getId())
        self.Refresh()

    def syncScene(self):
        """Bring the drawing options of the menus and the panel to the scene."""
        s = self.scene
        s.lowpass = self.parent.lowpass
        s.fillPoints = self.parent.fillPoints
        s.editionLevel = self.parent.editionLevel
        controls = self.parent.controls
        s.penWidth = controls.penWidth.GetValue()
        s.wanderSpeed = controls.wanderSpeed.GetValue()
        s.wanderPeriodicity = controls.wanderPeriodicity.GetValue()

    def setCurrentSize(self, size):
        self.Refresh()

    def SetColors(self, outline, bg, fill, rect, losa, wave):
        self.outlinecolor = wx.Colour(*outline)
        self.backgroundcolor = wx.Colour(*bg)
        self.fillcolor = wx.Colour(*fill)
        self.rectcolor = wx.Colour(*rect)
        self.losacolor = wx.Colour(*losa)
        self.wavecolor = wx.Colour(*wave)
        self.losaBrush = wx.Brush(self.losacolor, wx.SOLID)
        self.losaPen = wx.Pen(self.losacolor, width=1, style=wx.SOLID)

    # ------------------------------------------------------------------
    # the 3D view
    # ------------------------------------------------------------------
    def setView(self, view):
        if isinstance(view, int):
            view = space.VIEWS[view]
        self.camera.setView(view)
        self.notifyControls()
        self.Refresh()

    def setDrawOn(self, index):
        self.drawOn = int(index) % len(DRAW_SURFACES)
        self.notifyControls()
        self.Refresh()

    def setPenHeight(self, height):
        self.penHeight = max(-1.0, min(1.0, float(height)))
        self.Refresh()

    def setSphereRadius(self, radius):
        self.sphereRadius = max(0.1, min(1.7, float(radius)))
        self.Refresh()

    def notifyControls(self):
        controls = getattr(self.parent, "controls", None)
        if controls is not None and hasattr(controls, "syncSpaceTab"):
            controls.syncSpaceTab()

    def getViewState(self):
        state = self.camera.getState()
        state.update({"drawOn": self.drawOn, "penHeight": self.penHeight, "sphereRadius": self.sphereRadius})
        return state

    def setViewState(self, state):
        self.camera.setState(state)
        self.drawOn = int(state.get("drawOn", 0)) % len(DRAW_SURFACES)
        self.penHeight = float(state.get("penHeight", 0.0))
        self.sphereRadius = float(state.get("sphereRadius", 1.0))
        self.notifyControls()
        self.Refresh()

    def sceneYaw(self):
        audio = getattr(self.parent, "sg_audio", None)
        if audio is None:
            return 0.0
        try:
            return audio.sceneYaw()
        except Exception:
            return 0.0

    def surfaceKind(self):
        """What the pen draws on right now: 'floor', 'sphere' or 'view'."""
        if self.drawOn == 1:
            return 'sphere'
        if self.drawOn == 2 or self.camera.view in ('Front', 'Side'):
            return 'view'
        return 'floor'

    def moveKind(self):
        """The plane things are dragged in: level, or facing you in the side views."""
        if self.drawOn == 2 or self.camera.view in ('Front', 'Side'):
            return 'view'
        return 'floor'

    def planeNormal(self, kind):
        if kind == 'floor':
            return np.array([0.0, 0.0, 1.0])
        return self.camera.basis()[2]

    def pointAt(self, sx, sy, kind=None):
        """The point of the room under a pixel, on the drawing surface."""
        origin, direction = self.camera.ray(sx, sy)
        kind = kind or self.surfaceKind()
        if kind == 'sphere':
            hit = space.ray_sphere(origin, direction, self.sphereRadius)
        elif kind == 'floor':
            hit = space.ray_plane(origin, direction, (0.0, 0.0, self.penHeight), (0.0, 0.0, 1.0))
        else:
            anchor = (0.0, 0.0, self.penHeight) if self.camera.view == 'Top' else (0.0, 0.0, 0.0)
            hit = space.ray_plane(origin, direction, anchor, self.camera.basis()[2])
        if hit is None:
            return None
        return self.clipRoom(hit)

    def clipRoom(self, p):
        return np.array([min(max(p[0], -1.0), 1.0), min(max(p[1], -1.0), 1.0),
                         min(max(p[2], -space.HEIGHT / space.HALF), space.HEIGHT / space.HALF)])

    def movePen(self, point, prev, now, lift, kind, clip=True):
        """Drag a point of the room from pixel 'prev' to pixel 'now'.

        With lift the point leaves its surface: straight up or down from a
        level plane, in or out on the sphere, towards you or away on the view
        plane. Moving step by step lets the two be mixed in one gesture.
        """
        p = np.array(point, dtype=float)
        if lift:
            amount = (prev[1] - now[1]) / max(self.camera.pixelsPerUnit(p), 1e-6)
            if kind == 'sphere':
                r = float(np.linalg.norm(p))
                if r > 1e-6:
                    r2 = min(max(r + amount, 0.05), 1.7)
                    p = p * (r2 / r)
                    self.penRadius = r2
            elif kind == 'floor':
                p[2] += amount
            else:
                p = p - self.camera.basis()[2] * amount
        else:
            if kind == 'sphere':
                origin, direction = self.camera.ray(*now)
                hit = space.ray_sphere(origin, direction, self.penRadius)
                if hit is not None:
                    p = hit
            else:
                normal = self.planeNormal(kind)
                o1, d1 = self.camera.ray(*prev)
                o2, d2 = self.camera.ray(*now)
                h1 = space.ray_plane(o1, d1, p, normal)
                h2 = space.ray_plane(o2, d2, p, normal)
                if h1 is not None and h2 is not None:
                    delta = h2 - h1
                    if np.linalg.norm(delta) < 1.5:
                        p = p + delta
        return self.clipRoom(p) if clip else p

    def canvasPoint(self, room_point):
        return tuple(float(v) for v in space.room_to_canvas(np.asarray(room_point, dtype=float)))

    def roomPoint(self, canvas_point):
        return space.canvas_to_room(np.asarray(canvas_point, dtype=float)[:3])

    def toScreen(self, canvas_point):
        xy, depth = self.camera.project(self.roomPoint(canvas_point))
        return float(xy[0]), float(xy[1])

    def shapeBasis(self, room_point, kind):
        """The plane a circle, oscillation or spiral is drawn in, as canvas vectors."""
        if kind == 'floor':
            return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        if kind == 'view':
            right, up, forward = self.camera.basis()
            return (cv(right), cv(-up), cv(-forward))
        w = np.asarray(room_point, dtype=float)
        length = np.linalg.norm(w)
        w = w / length if length > 1e-9 else np.array([0.0, 1.0, 0.0])
        u = np.cross([0.0, 0.0, 1.0], w)
        if np.linalg.norm(u) < 1e-6:
            u = np.array([1.0, 0.0, 0.0])
        u = u / np.linalg.norm(u)
        v = np.cross(w, u)
        return (cv(u), cv(v), cv(w))

    # ------------------------------------------------------------------
    def hitHandle(self, pos, canvas_point, radius):
        x, y = self.toScreen(canvas_point)
        return abs(pos[0] - x) <= radius and abs(pos[1] - y) <= radius

    def hitPoint(self, pos, t, radius=5):
        """Index of the point of a trajectory under the pointer, or None."""
        pts = t.getPoints()
        if not pts:
            return None
        xy, depth = self.camera.project(space.canvas_to_room(np.asarray(pts, dtype=float)))
        d = np.maximum(np.abs(xy[:, 0] - pos[0]), np.abs(xy[:, 1] - pos[1]))
        index = int(np.argmin(d))
        return index if d[index] <= radius else None

    def ballScreen(self, ball):
        """(x, y, radius) of a ball in pixels."""
        centre = self.roomPoint(ball.getCenter())
        xy, depth = self.camera.project(centre)
        radius = ball.halfSize / space.HALF * self.camera.pixelsPerUnit(centre)
        return float(xy[0]), float(xy[1]), float(radius)

    def ballInside(self, ball, pos, small=False):
        x, y, radius = self.ballScreen(ball)
        hyp = math.hypot(x - pos[0], y - pos[1])
        if small:
            return hyp < max(radius / 3.0, 6.0)
        return hyp < radius

    def OnLeave(self, evt):
        self.pointerPos = None
        self.hover = None
        self.Refresh()
        evt.Skip()

    def OnCaptureLost(self, evt):
        self.action = None

    def OnResize(self, evt):
        w, h = self.GetClientSize()
        self.camera.setSize(w, h)
        wx.CallAfter(self.Refresh)
        evt.Skip()

    # ------------------------------------------------------------------
    # FX balls
    # ------------------------------------------------------------------
    def detachBall(self, key):
        old = self.fxballs.get(key)
        if old is not None and old.gui is not None:
            old.gui.Destroy()
            old.gui = None

    def attachBall(self, ball, load=None):
        self.pictures[ball.id] = BallPicture(ball)
        ball.gui = FxBallControls(self.parent, ball, self.parent.sg_audio)
        if load:
            ball.gui.load(load)
        else:
            ball.sliders["slider1"] = ball.gui.slider1.GetValue()
            ball.sliders["slider2"] = ball.gui.slider2.GetValue()
        self.scene.applyBallSliders(ball)

    def restoreFxBall(self, dict):
        self.detachBall(dict["id"])
        ball = self.scene.restoreFxBall(dict)
        self.attachBall(ball, dict.get("controls"))
        self.Refresh()

    def restoreFxBalls(self, dict, xfac=1.0, yfac=1.0):
        if dict != {}:
            for dic in dict.values():
                self.detachBall(dic["id"])
                ball = self.scene.restoreFxBall(dic, xfac, yfac)
                controls = dic.get("controls")
                if "pos" in dic and "center" not in dic and controls:
                    # SoundGrain's fourth slider was a pan: start from the default spread
                    controls = {k: v for k, v in controls.items() if k != "slider4"}
                self.attachBall(ball, controls)
            self.Refresh()

    def addFxBall(self, fx):
        ball = self.scene.addFxBall(fx)
        if ball is not None:
            self.attachBall(ball)
            self.Refresh()

    def removeAllFxBalls(self):
        for key in list(self.fxballs.keys()):
            self.removeFxBall(key)

    def removeFxBall(self, key):
        ball = self.fxballs.get(key)
        if ball is None:
            return
        if ball.gui is not None:
            ball.gui.Destroy()
            ball.gui = None
        self.pictures.pop(key, None)
        self.scene.removeFxBall(key)
        self.Refresh()

    # ------------------------------------------------------------------
    # mouse
    # ------------------------------------------------------------------
    def buttonAt(self, pos):
        for rect, callback, active in self.buttons:
            if rect.Contains(wx.Point(int(pos[0]), int(pos[1]))):
                return callback
        return None

    def OnWheel(self, event):
        self.SetFocus()
        delta = event.GetWheelDelta()
        if not delta:
            return
        steps = event.GetWheelRotation() / float(delta)
        if self.HasCapture() and self.action in ('draw', 'drag', 'edit', 'drag_ball'):
            # pull the pen up or down while it is on the paper
            pos = self.lastMouse
            lifted = (pos[0], pos[1] - steps * 12.0)
            self.applyDrag(pos, lifted, True, event.ShiftDown())
            self.Refresh()
            return
        if self.HasCapture():
            return
        horizontal = event.GetWheelAxis() == wx.MOUSE_WHEEL_HORIZONTAL
        if horizontal or event.ShiftDown():
            if self.camera.view == "3D":
                self.camera.orbit(steps * 12.0 * (1 if horizontal else -1), 0)
        else:
            self.camera.dolly(steps)
        self.Refresh()

    def startOrbit(self, evt):
        self.action = 'orbit'
        self.lastMouse = tuple(evt.GetPosition())
        if not self.HasCapture():
            self.CaptureMouse()

    def OnMiddleDown(self, evt):
        self.SetFocus()
        self.startOrbit(evt)

    def OnRightDown(self, evt):
        self.SetFocus()
        pos = tuple(evt.GetPosition())
        for t in self.getActiveTrajectories():
            if t.getFirstPoint() is not None and self.hitHandle(pos, t.getFirstPoint(), 7):
                self.scene.clearTrajectory(t)
                self.parent.controls.setSelected(self.scene.selected.getId())
                self.parent.createTempFile()
                self.Refresh()
                return
        mouseState = wx.GetMouseState()
        mousePos = (mouseState.GetX(), mouseState.GetY())
        for fxball in self.fxballs.values():
            if self.ballInside(fxball, pos, small=True):
                if fxball.gui is not None:
                    fxball.gui.SetPosition(mousePos)
                    fxball.gui.Show()
                return
        # empty space: walk round the room
        self.startOrbit(evt)

    def OnRightUp(self, evt):
        if self.HasCapture() and self.action == 'orbit':
            self.ReleaseMouse()
            self.action = None
        evt.Skip()

    def MouseDoubleClick(self, evt):
        self.SetFocus()
        pos = tuple(evt.GetPosition())
        if self.buttonAt(pos) is not None:
            return
        for t in self.getActiveTrajectories():
            # Select or duplicate trajectory
            if t.getFirstPoint() is not None and self.hitHandle(pos, t.getFirstPoint(), 7):
                self.syncScene()
                new = self.scene.duplicateTrajectory(t)
                self.setSelected(new if new is not None else t)
                self.beginDrag(pos)
                return

        for key, fxball in list(self.fxballs.items()):
            if self.ballInside(fxball, pos, small=True):
                self.removeFxBall(key)
                break

        evt.Skip()

    def beginDrag(self, pos):
        t = self.scene.selected
        self.action = 'drag'
        self.penKind = self.moveKind()
        self.pen = self.roomPoint(t.getFirstPoint())
        self.dragStart = np.array(self.pen)
        self.curCenters = {traj.getId(): traj.getCenter() for traj in self.getActiveTrajectories()}
        for traj in self.getActiveTrajectories():
            traj.setInitPoints()
        self.lastMouse = pos
        if not self.HasCapture():
            self.CaptureMouse()

    def MouseDown(self, evt):
        self.SetFocus()
        pos = tuple(evt.GetPosition())
        self.lastMouse = pos
        self.downScreen = pos
        callback = self.buttonAt(pos)
        if callback is not None:
            callback()
            return
        if evt.AltDown() and not any(
                t.getFirstPoint() is not None and self.hitHandle(pos, t.getFirstPoint(), 7)
                for t in self.getActiveTrajectories()) and not any(
                self.ballInside(b, pos) for b in self.fxballs.values()):
            self.startOrbit(evt)
            return
        self.syncScene()
        for t in self.getActiveTrajectories():
            # Select or duplicate trajectory
            if t.getFirstPoint() is not None and self.hitHandle(pos, t.getFirstPoint(), 7):
                if evt.AltDown():
                    new = self.scene.duplicateTrajectory(t)
                    self.setSelected(new if new is not None else t)
                else:
                    self.setSelected(t)
                self.beginDrag(pos)
                return
            # Rescale circle, oscil or spiral trajectory
            if t.getType() in SHAPES and t.getPoints() and self.hitHandle(pos, t.getLosangePoint(), 5):
                self.setSelected(t)
                self.action = 'rescale'
                t.rescaleRadius = t.getRadius()
                t.setInitPoints()
                self.CaptureMouse()
                return
            # Check for trajectory transformation
            index = self.hitPoint(pos, t, 5)
            if index is not None:
                self.pindex = index
                self.setSelected(t)
                t.setInitPoints()
                self.action = 'edit'
                self.penKind = self.moveKind()
                self.pen = self.roomPoint(t.getPoints()[index])
                self.dragStart = np.array(self.pen)
                self.CaptureMouse()
                return
        # Check if inside an FxBall
        for key, fxball in list(self.fxballs.items()):
            if self.ballInside(fxball, pos, small=True):
                if evt.AltDown():
                    self.removeFxBall(key)
                else:
                    self.fxball = fxball
                    self.action = 'drag_ball'
                    self.penKind = self.moveKind()
                    self.pen = self.roomPoint(fxball.getCenter())
                    self.CaptureMouse()
                return
            elif self.ballInside(fxball, pos, small=False):
                if evt.AltDown():
                    self.removeFxBall(key)
                    self.Refresh()
                else:
                    self.fxball = fxball
                    self.action = 'rescale_ball'
                    self.CaptureMouse()
                return

        # Click in an empty space, draw a new trajectory
        start = self.pointAt(pos[0], pos[1])
        if start is None:
            return
        self.action = 'draw'
        self.penKind = self.surfaceKind()
        self.penRadius = self.sphereRadius
        self.pen = start
        kind = self.penKind
        sphere = self.sphereRadius if kind == 'sphere' else None
        self.traj = self.scene.beginDraw(self.canvasPoint(start), self.shapeBasis(start, kind), sphere)
        if self.traj is not None:
            self.CaptureMouse()
            self.Refresh()
        evt.Skip()

    def MouseUp(self, evt):
        if self.HasCapture():
            if self.action == 'orbit':
                self.ReleaseMouse()
                self.action = None
                return
            if self.action == 'draw' and self.traj:
                new = self.scene.endDraw(self.canvasPoint(self.pen))
                self.traj = None
                if new is None:
                    self.ReleaseMouse()
                    self.action = None
                    self.Refresh()
                    return
                self.parent.controls.setSelected(new.getId())
            elif self.action == 'drag':
                for traj in self.getActiveTrajectories():
                    traj.setInitPoints()
            elif self.action == 'rescale':
                self.scene.endRescale(self.selected)
            elif self.action == 'edit':
                self.scene.endEdit(self.selected)
            elif self.action in ['drag_ball', 'rescale_ball']:
                self.fxball.restoreGradient()
                self.fxball.gradient = self.fxball._gradient
                self.fxball.restoreCenter()
                self.scene.placeBall(self.fxball)
                self.parent.is_unsaved = True

            self.Refresh()
            self.ReleaseMouse()
            if self.action not in ['drag_ball', 'rescale_ball']:
                self.parent.createTempFile()
            self.action = None
            self.onMotion = False
        evt.Skip()

    def applyDrag(self, prev, now, lift, shift=False):
        """One step of whatever is being dragged, from pixel prev to pixel now."""
        if self.action == 'draw' and self.traj:
            self.pen = self.movePen(self.pen, prev, now, lift, self.penKind)
            if self.traj.getType() in SHAPES and lift:
                # lifting while making a shape raises the whole shape
                centre = self.traj.getCenter()
                moved = self.canvasPoint(self.pen)
                self.traj.setCenter((centre[0], centre[1], moved[2]) if self.penKind == 'floor' else centre)
            self.scene.drawTo(self.canvasPoint(self.pen))
        elif self.action == 'drag':
            self.pen = self.movePen(self.pen, prev, now, lift, self.penKind, clip=False)
            start = self.canvasPoint(self.dragStart)
            here = self.canvasPoint(self.pen)
            offset = tuple(start[k] - here[k] for k in range(3))
            t = self.selected
            self.scene.moveTrajectory(t, offset, self.curCenters.get(t.getId()))
            if shift:
                for traj in self.getActiveTrajectories():
                    if traj != t:
                        self.scene.moveTrajectory(traj, offset, self.curCenters.get(traj.getId()))
        elif self.action == 'edit':
            self.pen = self.movePen(self.pen, prev, now, lift, self.penKind)
            start = self.canvasPoint(self.dragStart)
            here = self.canvasPoint(self.pen)
            self.selected.editTraj(self.pindex, tuple(start[k] - here[k] for k in range(3)))
        elif self.action == 'drag_ball':
            if shift:
                self.fxball.setGradient(self.downScreen[1] - now[1])
                picture = self.pictures.get(self.fxball.id)
                if picture is not None:
                    picture.update()
            else:
                self.pen = self.movePen(self.pen, prev, now, lift, self.penKind)
                self.fxball.move(self.canvasPoint(self.pen))
                self.scene.placeBall(self.fxball)

    def MouseMotion(self, evt):
        pos = tuple(evt.GetPosition())
        self.pointerPos = pos
        prev = self.lastMouse
        if self.HasCapture() and self.action == 'orbit':
            if self.camera.view != "3D":
                self.camera.setView("3D")
                self.notifyControls()
            self.camera.orbit(pos[0] - prev[0], pos[1] - prev[1])
            self.lastMouse = pos
            self.Refresh()
            return
        if self.HasCapture() and evt.Dragging() and evt.LeftIsDown():
            lift = evt.CmdDown()
            if self.action in ('draw', 'drag', 'edit', 'drag_ball'):
                self.applyDrag(prev, pos, lift, evt.ShiftDown())
            elif self.action == 'rescale':
                t = self.selected
                centre = self.roomPoint(t.getCenter())
                normal = rv(t.getBasis()[2])
                length = np.linalg.norm(normal)
                origin, direction = self.camera.ray(pos[0], pos[1])
                hit = space.ray_plane(origin, direction, centre, normal / length) if length > 1e-9 else None
                if hit is not None:
                    self.scene.rescaleShape(t, float(np.linalg.norm(hit - centre)) * space.HALF)
            elif self.action == 'rescale_ball':
                x, y, radius = self.ballScreen(self.fxball)
                hyp = max(5.0, math.hypot(x - pos[0], y - pos[1]))
                ppu = self.camera.pixelsPerUnit(self.roomPoint(self.fxball.getCenter()))
                self.fxball.resize(hyp * 2.0 / max(ppu, 1e-6) * space.HALF)
            self.onMotion = True
            self.lastMouse = pos
            self.Refresh()
        else:
            self.lastMouse = pos
            if not self.HasCapture():
                self.hover = self.pointAt(pos[0], pos[1])
                self.Refresh()
        evt.Skip()

    # ------------------------------------------------------------------
    # keyboard
    # ------------------------------------------------------------------
    def KeyDown(self, evt):
        key = evt.GetKeyCode()
        if key == wx.WXK_ESCAPE:
            self.camera.reset()
            self.notifyControls()
            self.Refresh()
            evt.StopPropagation()
            return
        if key in [wx.WXK_BACK, wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE]:
            if self.selected != None:
                self.scene.clearTrajectory(self.selected)
                self.parent.controls.setSelected(self.scene.selected.getId())
                self.parent.createTempFile()
            evt.StopPropagation()
            return

        plain = not evt.ControlDown() and not evt.ShiftDown()
        if not evt.AltDown() and not evt.MetaDown():
            if key in (ord('D'), ord('d')) and plain:
                self.duplicateSelected()
                evt.StopPropagation()
                return
            if key in (ord('M'), ord('m')) and plain:
                self.mirrorSelected()
                evt.StopPropagation()
                return
            simple = {ord('H'): ('horizontal', 0), ord('V'): ('vertical', 0), ord('U'): ('updown', 0)}
            if key < 256 and ord(chr(key).upper()) in simple and plain:
                self.transformSelected(*simple[ord(chr(key).upper())])
                evt.StopPropagation()
                return
            turning = {ord('R'): 'rotate', ord('X'): 'tiltx', ord('Y'): 'tilty'}
            if key < 256 and ord(chr(key).upper()) in turning and (not evt.ControlDown() or evt.ShiftDown()):
                angle = 1 if evt.ControlDown() else 5 if evt.ShiftDown() else 15
                self.transformSelected(turning[ord(chr(key).upper())], angle)
                evt.StopPropagation()
                return
            if key < 256 and chr(key).upper() == 'Z' and plain:
                self.transformSelected('sphere', self.sphereRadius)
                evt.StopPropagation()
                return
            if key < 256 and chr(key).upper() == 'B' and plain:
                self.transformSelected('flatten')
                evt.StopPropagation()
                return
            if key < 256 and chr(key) in '[]' and plain:
                level = self.parent.arrowSpeedLevel
                self.transformSelected('lift', (10 if chr(key) == ']' else -10) * level)
                evt.StopPropagation()
                return
            if key < 256 and chr(key) in '-=' and plain:
                self.transformSelected('scale', 1.05 if chr(key) == '=' else 1 / 1.05)
                evt.StopPropagation()
                return
            views = {'P': '3D', 'T': 'Top', 'F': 'Front', 'S': 'Side'}
            if key < 256 and chr(key).upper() in views and plain:
                self.setView(views[chr(key).upper()])
                evt.StopPropagation()
                return
            if key < 256 and chr(key).upper() == 'G' and plain:
                self.setDrawOn(self.drawOn + 1)
                evt.StopPropagation()
                return

        level = self.parent.arrowSpeedLevel
        if evt.CmdDown():
            # Cmd/Ctrl + up and down: height
            off = {wx.WXK_UP: [0,0,-level], wx.WXK_DOWN: [0,0,level]}.get(key, [0,0,0])
        else:
            off = {wx.WXK_UP: [0,level,0], wx.WXK_DOWN: [0,-level,0], wx.WXK_LEFT: [level,0,0],
                   wx.WXK_RIGHT: [-level,0,0]}.get(key, [0,0,0])
        # Move selected trajectory
        if evt.ShiftDown() and off != [0,0,0]:
            traj = self.trajectories[min(self.parent.controls.getSelected(), MAX_STREAMS - 1)]
            traj.setInitPoints()
            self.scene.moveTrajectory(traj, off, traj.getCenter())
            traj.setInitPoints()
            self.onMotion = True
            self.Refresh()
            evt.StopPropagation()
            return
        # Move all trajectories
        elif off != [0,0,0]:
            for traj in self.getActiveTrajectories():
                traj.setInitPoints()
                self.scene.moveTrajectory(traj, off, traj.getCenter())
                traj.setInitPoints()
            self.onMotion = True
            self.Refresh()
            evt.StopPropagation()
            return
        # Set freeze mode
        if key < 256:
            c = chr(key)
            if c in ['1', '2', '3', '4', '5', '6', '7', '8']:
                if self.trajectories[int(c)-1].getFreeze():
                    self.trajectories[int(c)-1].setFreeze(False)
                else:
                    self.trajectories[int(c)-1].setFreeze(True)
            elif c == '0':
                for i in range(8):
                    if self.trajectories[i].getFreeze():
                        self.trajectories[i].setFreeze(False)
                    else:
                        self.trajectories[i].setFreeze(True)
            elif c == '9':
                if not self.useMario:
                    self.useMario = True
                else:
                    self.useMario = False
        evt.Skip()

    def duplicateSelected(self):
        t = self.selected
        if self.HasCapture() or t is None or not t.getActive() or len(t.getPoints()) < 2:
            return None
        self.syncScene()
        new = self.scene.duplicateTrajectory(t)
        if new is not None:
            self.setSelected(new)
            self.parent.createTempFile()
            self.Refresh()
        return new

    def mirrorSelected(self):
        """A twin of the selected trajectory mirrored left to right (the paired
        sound lines of Bernhard Leitner's rooms)."""
        t = self.selected
        if self.HasCapture() or t is None or not t.getActive() or len(t.getPoints()) < 2:
            return None
        self.syncScene()
        new = self.scene.duplicateTrajectory(t)
        if new is not None:
            new.setPoints([(space.CANVAS - p[0], p[1], p[2]) for p in new.getPoints()])
            if new.getCenter() is not None:
                c = new.getCenter()
                new.setCenter((space.CANVAS - c[0], c[1], c[2]))
                new.setBasis(*[(-v[0], v[1], v[2]) for v in new.getBasis()])
                new.geometryTransformed = True
            self.setSelected(new)
            self.parent.createTempFile()
            self.Refresh()
        return new

    def transformSelected(self, operation, amount=0):
        trajectory = self.selected
        if self.HasCapture():
            return
        if self.scene.transform(trajectory, operation, amount):
            self.parent.createTempFile()
            self.Refresh()

    def KeyUp(self, evt):
        self.onMotion = False
        if evt.GetKeyCode() in [wx.WXK_BACK, wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE, wx.WXK_UP, wx.WXK_DOWN, wx.WXK_LEFT, wx.WXK_RIGHT]:
            self.Refresh()

    # ------------------------------------------------------------------
    # drawing
    # ------------------------------------------------------------------
    def P(self, room_points):
        xy, depth = self.camera.project(np.asarray(room_points, dtype=float))
        return xy

    def lines(self, gc, room_points):
        xy = self.P(room_points)
        if len(xy) > 1:
            gc.StrokeLines([wx.Point2D(float(x), float(y)) for x, y in xy])

    def segments(self, gc, starts, ends):
        a = self.P(starts)
        b = self.P(ends)
        if len(a):
            gc.StrokeLineSegments([wx.Point2D(float(x), float(y)) for x, y in a],
                                  [wx.Point2D(float(x), float(y)) for x, y in b])

    def circle(self, radius=1.0, height=0.0, count=96, plane='floor'):
        a = np.linspace(0, 2 * math.pi, count + 1)
        if plane == 'floor':
            return np.stack([np.cos(a) * radius, np.sin(a) * radius, np.full_like(a, height)], axis=1)
        if plane == 'front':
            return np.stack([np.cos(a) * radius, np.zeros_like(a), np.sin(a) * radius], axis=1)
        return np.stack([np.zeros_like(a), np.cos(a) * radius, np.sin(a) * radius], axis=1)

    def mkpen(self, colour, alpha=255, width=1):
        return wx.Pen(wx.Colour(colour[0], colour[1], colour[2], alpha), width=width, style=wx.SOLID)

    def drawRoom(self, gc):
        white = (self.outlinecolor.Red(), self.outlinecolor.Green(), self.outlinecolor.Blue())
        top = space.HEIGHT / space.HALF
        # the grid of the floor (ear level): SoundGrain's surface
        ticks = np.linspace(-1, 1, 9)
        gc.SetPen(self.mkpen(white, 16))
        self.segments(gc, [(t, -1, 0) for t in ticks] + [(-1, t, 0) for t in ticks],
                      [(t, 1, 0) for t in ticks] + [(1, t, 0) for t in ticks])
        # the room above and below
        gc.SetPen(self.mkpen(white, 26))
        corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
        for z in (-top, top):
            self.lines(gc, [(x, y, z) for x, y in corners + corners[:1]])
        self.segments(gc, [(x, y, -top) for x, y in corners], [(x, y, top) for x, y in corners])
        # the edge of SoundGrain's surface
        gc.SetPen(self.mkpen(white, 150))
        self.lines(gc, [(x, y, 0) for x, y in corners + corners[:1]])

    def drawWaveform(self, gc):
        if not self.sndBitmap or not self.waveform:
            return
        gc.SetPen(wx.Pen("#3F3F44"))
        source = self.scene.xSource
        for samples in self.waveform:
            if len(samples) < 2:
                continue
            if source == 1:
                # the sound laid round the listener, clockwise from the front
                theta = samples[:, 0] / space.CANVAS * 2 * math.pi
                rho = 0.78 + (space.HALF - samples[:, 1]) / space.HALF * 0.2
                pts = np.stack([np.sin(theta) * rho, np.cos(theta) * rho, np.zeros_like(rho)], axis=1)
            elif source == 0:
                pts = space.canvas_to_room(np.column_stack([samples, np.zeros(len(samples))]))
            else:
                continue
            self.lines(gc, pts)

    def drawSphere(self, gc):
        white = (self.outlinecolor.Red(), self.outlinecolor.Green(), self.outlinecolor.Blue())
        gc.SetPen(self.mkpen(white, 70))
        self.lines(gc, self.circle(1.0))
        gc.SetPen(self.mkpen(white, 28))
        self.lines(gc, self.circle(1.0, plane='front'))
        self.lines(gc, self.circle(1.0, plane='side'))
        for el in (30, 60, -30, -60):
            r, h = math.cos(math.radians(el)), math.sin(math.radians(el))
            gc.SetPen(self.mkpen(white, 14))
            self.lines(gc, self.circle(r, h, 72))
        kind = self.surfaceKind()
        blue = (self.losacolor.Red(), self.losacolor.Green(), self.losacolor.Blue())
        if kind == 'sphere':
            # the sphere the pen draws on
            gc.SetPen(self.mkpen((90, 150, 255), 150))
            self.lines(gc, self.circle(self.sphereRadius))
            gc.SetPen(self.mkpen((90, 150, 255), 70))
            self.lines(gc, self.circle(self.sphereRadius, plane='front'))
            self.lines(gc, self.circle(self.sphereRadius, plane='side'))
        elif kind == 'floor' and abs(self.penHeight) > 1e-3:
            gc.SetPen(self.mkpen((90, 150, 255), 110))
            corners = [(-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1)]
            self.lines(gc, [(x, y, self.penHeight) for x, y in corners])

    def drawListener(self, gc):
        yaw = -self.sceneYaw()          # turning the scene one way is turning the head the other
        c, s = math.cos(yaw), math.sin(yaw)

        def turn(p):
            # yaw is to the left (counter-clockwise seen from above)
            return (p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2])

        head = [turn(p) for p in self.circle(0.055, 0.0, 24)]
        nose = [turn(p) for p in [(-0.03, 0.045, 0), (0, 0.1, 0), (0.03, 0.045, 0)]]
        gc.SetPen(self.mkpen((230, 230, 230), 220, 1))
        self.lines(gc, head)
        self.lines(gc, nose)
        audio = getattr(self.parent, "sg_audio", None)
        if audio is None:
            return
        speakers = audio.speakerDirections()
        if not speakers:
            return
        gc.SetFont(self.font, wx.Colour(20, 20, 20))
        gc.SetPen(self.mkpen((200, 200, 200), 255))
        gc.SetBrush(wx.Brush(wx.Colour(200, 200, 200)))
        pts = self.P([turn(p) for p in speakers])
        floor = self.P([turn((p[0], p[1], 0.0)) for p in speakers])
        gc.SetPen(self.mkpen((200, 200, 200), 60))
        gc.StrokeLineSegments([wx.Point2D(float(x), float(y)) for x, y in pts],
                              [wx.Point2D(float(x), float(y)) for x, y in floor])
        gc.SetPen(self.mkpen((200, 200, 200), 255))
        for index, (x, y) in enumerate(pts):
            gc.DrawRectangle(x - 6, y - 6, 12, 12)
            label = str(index + 1)
            tw, th = gc.GetTextExtent(label)[:2]
            gc.DrawText(label, x - tw / 2.0, y - th / 2.0)

    def drawBalls(self, gc):
        for key, ball in list(self.fxballs.items()):
            picture = self.pictures.get(key)
            if picture is None:
                continue
            x, y, radius = self.ballScreen(ball)
            bit = picture.update()
            gc.DrawBitmap(bit, x - radius, y - radius, radius * 2, radius * 2)
            # where it stands: a foot on the floor
            centre = self.roomPoint(ball.getCenter())
            if abs(centre[2]) > 0.01:
                first, _ = getColorsFor(ball.getFx())
                gc.SetPen(self.mkpen(first, 90))
                self.segments(gc, [centre], [(centre[0], centre[1], 0.0)])

    def trajPens(self, t):
        colour = t.getColour()
        return colour, wx.Colour(*colour)

    def drawTrajectories(self, gc):
        selectedTraj = self.parent.controls.getSelected()
        activeTrajs = [t for t in self.getActiveTrajectories() if len(t.getPoints()) > 1]
        handles = []
        for t in activeTrajs:
            if t.getId() == selectedTraj:
                self.scene.selected = t
            colour, wxcolour = self.trajPens(t)
            pts = np.asarray(t.getPoints(), dtype=float)
            room = space.canvas_to_room(pts)
            if np.any(np.abs(room[:, 2]) > 0.004):
                # its shadow on the floor and a few stems say how high it is
                floor = np.array(room)
                floor[:, 2] = 0.0
                gc.SetPen(self.mkpen(colour, 70))
                self.lines(gc, floor)
                every = max(1, len(room) // 16)
                gc.SetPen(self.mkpen(colour, 55))
                self.segments(gc, room[::every], floor[::every])
            xy = self.P(room)
            if t.getWidth() > 2:
                middle = room[len(room) // 2]
                width = max(2.0, t.getWidth() / space.HALF * self.camera.pixelsPerUnit(middle))
                pen = wx.Pen(wx.Colour(colour[0], colour[1], colour[2], 100), width=int(round(width)))
                pen.SetCap(wx.CAP_BUTT)
                pen.SetJoin(wx.JOIN_ROUND)
                gc.SetPen(pen)
            else:
                gc.SetPen(wx.Pen(wxcolour, width=2, style=wx.SOLID))
            gc.StrokeLines([wx.Point2D(float(x), float(y)) for x, y in xy])
            if t.getWidth() > 2:
                gc.SetPen(wx.Pen(wxcolour, width=1, style=wx.SOLID))
                gc.StrokeLines([wx.Point2D(float(x), float(y)) for x, y in xy])
            handles.append((t, xy))

        # Labels and handles remain a consistent size on screen.
        gc.SetFont(self.font, wx.Colour(0, 0, 0))
        for t, xy in handles:
            colour, wxcolour = self.trajPens(t)
            x, y = xy[0]
            gc.SetBrush(wx.Brush(wxcolour, style=wx.SOLID))
            gc.SetPen(wx.Pen("#EEEEEE", width=2) if t.getId() == selectedTraj else wx.Pen(wxcolour, width=1))
            gc.DrawRoundedRectangle(x-7, y-7, 14, 14, 2)
            label = str(t.getLabel())
            tw, th = gc.GetTextExtent(label)[:2]
            gc.DrawText(label, x - tw / 2.0, y - th / 2.0)
            if t.getType() in SHAPES:
                x, y = xy[int(len(xy) * 2 / 3)]
                gc.SetBrush(self.losaBrush)
                gc.SetPen(self.losaPen)
                gc.DrawRoundedRectangle(x-5, y-5, 10, 10, 2)

    def drawPlayheads(self, gc, dc=None):
        activeTrajs = [t for t in self.getActiveTrajectories() if len(t.getPoints()) > 1 and t.circlePos]
        for t in activeTrajs:
            pos = t.circlePos
            if pos is None:
                continue
            try:
                room = self.roomPoint(pos)
                x, y = self.P(room)
                colour, wxcolour = self.trajPens(t)
                if abs(room[2]) > 0.004:
                    fx, fy = self.P((room[0], room[1], 0.0))
                    gc.SetPen(self.mkpen(colour, 150))
                    gc.StrokeLine(x, y, fx, fy)
                    gc.SetBrush(wx.Brush(wx.Colour(colour[0], colour[1], colour[2], 150)))
                    gc.DrawEllipse(fx - 3, fy - 1.5, 6, 3)
                if self.useMario and dc is not None:
                    last = t.lastCirclePos or pos
                    lx, ly = self.P(self.roomPoint(last))
                    marioff = 0 if lx < x else 4
                    dc.DrawBitmap(self.marios[t.mario + marioff], int(x-8), int(y-8), True)
                    continue
                gc.SetPen(wx.Pen(wxcolour.ChangeLightness(80), width=2))
                gc.SetBrush(wx.Brush(wxcolour.ChangeLightness(110)))
                gc.DrawEllipse(x-5.5, y-5.5, 11, 11)
                border = wx.Colour(*t.getBorderColour())
                gc.SetPen(wx.Pen(border, width=1))
                gc.SetBrush(wx.Brush(border))
                gc.DrawEllipse(x-2, y-2, 4, 4)
            except Exception:
                # With midi triggering a trajectory can vanish in the middle of this block.
                pass

    def drawPenCursor(self, gc):
        point = self.pen if (self.HasCapture() and self.action in ('draw', 'edit', 'drag', 'drag_ball')) else self.hover
        if point is None or self.pointerPos is None:
            return
        x, y = self.P(point)
        fx, fy = self.P((point[0], point[1], 0.0))
        gc.SetPen(self.mkpen((140, 190, 255), 170))
        if abs(point[2]) > 0.004:
            gc.StrokeLine(x, y, fx, fy)
        a = self.P((point[0] - 0.05, point[1], 0.0))
        b = self.P((point[0] + 0.05, point[1], 0.0))
        c = self.P((point[0], point[1] - 0.05, 0.0))
        d = self.P((point[0], point[1] + 0.05, 0.0))
        gc.StrokeLine(a[0], a[1], b[0], b[1])
        gc.StrokeLine(c[0], c[1], d[0], d[1])
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.DrawEllipse(x - 3, y - 3, 6, 6)

    def drawButtons(self, gc):
        self.buttons = []
        gc.SetFont(self.font, wx.Colour(225, 225, 225))
        rows = [("view", space.VIEWS, lambda name: self.camera.view == name,
                 lambda name: (lambda: self.setView(name))),
                ("draw on", DRAW_SURFACES, lambda name: DRAW_SURFACES[self.drawOn] == name,
                 lambda name: (lambda: self.setDrawOn(DRAW_SURFACES.index(name))))]
        y = 6
        for caption, names, active, action in rows:
            gc.SetFont(self.font, wx.Colour(150, 150, 150))
            tw, th = gc.GetTextExtent(caption)[:2]
            gc.DrawText(caption, 8, y + (18 - th) / 2.0)
            x = 58
            for name in names:
                tw, th = gc.GetTextExtent(name)[:2]
                width = tw + 14
                on = active(name)
                gc.SetPen(wx.Pen(wx.Colour(200, 200, 200, 200 if on else 90), 1))
                gc.SetBrush(wx.Brush(wx.Colour(184, 32, 32, 230) if on else wx.Colour(60, 60, 60, 180)))
                gc.DrawRoundedRectangle(x, y, width, 18, 3)
                gc.SetFont(self.font, wx.Colour(255, 255, 255) if on else wx.Colour(200, 200, 200))
                gc.DrawText(name, x + 7, y + (18 - th) / 2.0)
                self.buttons.append((wx.Rect(int(x), int(y), int(width), 18), action(name), on))
                x += width + 4
            y += 22

    def drawReadout(self, gc):
        point = self.pen if (self.HasCapture() and self.action in ('draw', 'edit', 'drag', 'drag_ball')) else self.hover
        if point is None or self.pointerPos is None:
            return
        w, h = self.GetClientSize()
        canvas = self.canvasPoint(point)
        x, y = space.grain_xy(canvas, 0.0, 0, 0)
        az, el, dist = space.azel_dist(point)
        text = "X: %.3f  Y: %.3f  Z: %+.2f   az %+.0f  el %+.0f  d %.2f" % (
            x * self.parent.controls.sndDur, y, point[2], az, el, dist)
        gc.SetFont(self.font_pos, wx.Colour(255, 255, 255))
        tw, th = gc.GetTextExtent(text)[:2]
        gc.DrawText(text, w - tw - 8, h - th - 4)

    def draw(self, dc, overlay=True):
        """Paint the whole room into a device context."""
        width, height = dc.GetSize() if not isinstance(dc, wx.PaintDC) else self.GetClientSize()
        width, height = self.GetClientSize() if self.GetClientSize().width > 0 else (width, height)
        self.camera.setSize(width, height)
        dc.SetBackground(wx.Brush(self.backgroundcolor))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        self.drawRoom(gc)
        self.drawWaveform(gc)
        self.drawSphere(gc)
        self.drawListener(gc)
        self.drawBalls(gc)
        self.drawTrajectories(gc)
        self.drawPlayheads(gc, dc if self.useMario else None)
        if overlay:
            self.drawPenCursor(gc)
            self.drawReadout(gc)
            self.drawButtons(gc)

    def OnPaint(self, evt):
        dc = self.dcref(self)
        try:
            self.draw(dc)
        except Exception:
            import traceback
            traceback.print_exc()
        self.needBitmap = False

    def snapshot(self, path, size=None):
        """Save a picture of the room as a PNG (used by the self-test and the manual)."""
        w, h = size or tuple(self.GetClientSize())
        bitmap = wx.Bitmap(int(w), int(h))
        dc = wx.MemoryDC(bitmap)
        self.draw(dc, overlay=True)
        dc.SelectObject(wx.NullBitmap)
        bitmap.SaveFile(path, wx.BITMAP_TYPE_PNG)
        return path

    # ------------------------------------------------------------------
    # the waveform on the floor
    # ------------------------------------------------------------------
    def analyse(self, file):
        self.file = file
        self.list = self.parent.sg_audio.getViewTable((int(space.CANVAS), int(space.CANVAS)))
        self.bitmapDict[self.file] = self.list
        self.create_bitmap()

    def create_bitmap(self):
        self.waveform = [np.asarray(samples, dtype=float) for samples in self.list if len(samples)]
        self.sndBitmap = True
        self.needBitmap = True
        self.Refresh()


def getColorsFor(fx):
    from .FxBall import getColors
    first, second = getColors(fx, 30)
    return (first.Red(), first.Green(), first.Blue()), second
