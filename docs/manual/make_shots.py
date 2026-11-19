"""Takes the pictures of the manual from the real application (macOS).

    python docs/manual/make_shots.py ["output device"]

Without a device it runs on pyo's offline server (no audio device is opened).

Starts Sondugrande with the example project, plays it, and photographs its own
windows (by window number, so nothing else on the screen is in the picture)
and the room in its different states. Needs the Xcode command line tools for
the small Swift helper that finds the windows.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

DEVICE = sys.argv[1] if len(sys.argv) > 1 else ""
if not DEVICE:
    os.environ["SONDUGRANDE_AUDIO"] = "offline"
work = tempfile.mkdtemp(prefix="sondugrande_shots_")
prefs = os.path.join(work, "prefs.txt")
with open(prefs, "w") as f:
    f.write("audioDriver=%s\nmidiDriver=\nsamplePrecision=32-bit\nlastFilePath=%s\nlastAudioPath=%s\n" % (DEVICE, work, work))
os.environ["SONDUGRANDE_PREFS"] = prefs

import numpy as np                      # noqa: E402
import wx                               # noqa: E402
from sondugrande import app as application, space      # noqa: E402

helper = os.path.join(work, "winlist")
subprocess.check_call(["swiftc", "-O", os.path.join(HERE, "winlist.swift"), "-o", helper])


def windows():
    out = subprocess.run([helper, str(os.getpid())], capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            rows.append((int(parts[0]), int(parts[1]), int(parts[2]), parts[3]))
    return rows


def photograph(title, name):
    for number, width, height, text in windows():
        if text.startswith(title):
            subprocess.check_call(["screencapture", "-x", "-o", "-l%d" % number, os.path.join(HERE, name)])
            print(name)
            return True
    print("window not found: %s  %s" % (title, windows()))
    return False


class Shots:
    def __init__(self):
        self.app = application.SondugrandeApp(redirect=False)
        self.frame = self.app.frame
        self.frame.Show()
        self.panel = self.frame.panel
        self.controls = self.frame.controls
        self.audio = self.frame.sg_audio
        self.steps = [self.load, self.play, self.window, self.rooms, self.pen, self.sphere, self.azimuth,
                      self.stop, self.speakers, self.speakersShot, self.spaceWindow, self.settingsWindow, self.done]
        wx.CallLater(800, self.next)

    def next(self):
        if not self.steps:
            return
        step = self.steps.pop(0)
        wait = step() or 400
        if step is not self.done:
            wx.CallLater(int(wait), self.next)

    def mouse(self, kind, x, y, cmd=False):
        evt = wx.MouseEvent(kind)
        evt.SetPosition(wx.Point(int(round(x)), int(round(y))))
        evt.SetLeftDown(kind != wx.wxEVT_LEFT_UP)
        evt.SetControlDown(cmd)
        {wx.wxEVT_LEFT_DOWN: self.panel.MouseDown, wx.wxEVT_MOTION: self.panel.MouseMotion,
         wx.wxEVT_LEFT_UP: self.panel.MouseUp}[kind](evt)

    def pixels(self, room_points):
        xy, depth = self.panel.camera.project(np.asarray(room_points, dtype=float))
        return [(float(x), float(y)) for x, y in xy]

    def load(self):
        self.frame.loadFile(os.path.join(ROOT, "examples", "demo.sgr"))
        return 1500

    def play(self):
        event = wx.CommandEvent(wx.wxEVT_TOGGLEBUTTON)
        event.SetInt(1)
        self.controls.handleAudio(event)
        self.frame.Raise()
        return 2600

    def window(self):
        photograph("Sondugrande", "window.png")

    def rooms(self):
        for view in ("3D", "Top", "Front", "Side"):
            self.panel.setView(view)
            self.panel.snapshot(os.path.join(HERE, "room_%s.png" % view.lower()), 2)
        self.panel.setView("3D")

    def pen(self):
        # a free-hand line being drawn on the floor and pulled up half way: the picture is taken with the pen still down
        self.controls.setType(0)
        for front in (-0.55, -0.4, -0.7, -0.3):
            pts = self.pixels(np.stack([np.linspace(-0.75, 0.3, 48), front + 0.08 * np.sin(np.linspace(0, 6, 48)),
                                        np.zeros(48)], axis=1))
            if not any(self.panel.hitPoint(pts[0], t, 9) is not None for t in self.panel.getActiveTrajectories()):
                break
        self.mouse(wx.wxEVT_LEFT_DOWN, *pts[0])
        for x, y in pts[1:24]:
            self.mouse(wx.wxEVT_MOTION, x, y)
        px, py = pts[23]
        for k in range(1, 13):
            self.mouse(wx.wxEVT_MOTION, px, py - 9 * k, cmd=True)
        for x, y in pts[24:]:
            self.mouse(wx.wxEVT_MOTION, x, y - 108)
        self.panel.snapshot(os.path.join(HERE, "room_pen.png"), 2)
        self.mouse(wx.wxEVT_LEFT_UP, pts[-1][0], pts[-1][1] - 108)
        self.drawn = self.panel.selected
        self.controls.setType(0)

    def sphere(self):
        # drawing on the sphere: a free line on the side that faces the camera
        self.panel.scene.clearTrajectory(self.drawn)
        self.controls.setSelected(0)
        self.panel.setDrawOn(1)
        eye = self.panel.camera.eye()
        eye = eye / np.linalg.norm(eye)
        right, up, forward = self.panel.camera.basis()
        a = np.linspace(-1.0, 1.0, 60)
        # start where nothing is: a press on a trajectory would pull it instead of drawing
        for lift in (0.25, 0.4, 0.55, 0.7, 0.1, -0.1):
            pts = [eye + right * (0.75 * t) + up * (0.3 * np.sin(t * 3.0) + lift) for t in a]
            pts = [p / np.linalg.norm(p) for p in pts]
            px = self.pixels(pts)
            if not any(self.panel.hitPoint(px[0], t, 9) is not None for t in self.panel.getActiveTrajectories()) \
                    and not any(self.panel.ballInside(b, px[0]) for b in self.panel.fxballs.values()):
                break
        self.mouse(wx.wxEVT_LEFT_DOWN, *px[0])
        for x, y in px[1:]:
            self.mouse(wx.wxEVT_MOTION, x, y)
        self.panel.snapshot(os.path.join(HERE, "room_sphere.png"), 2)
        self.mouse(wx.wxEVT_LEFT_UP, *px[-1])
        self.panel.scene.clearTrajectory(self.panel.selected)
        self.controls.setSelected(0)
        self.panel.setDrawOn(0)

    def azimuth(self):
        self.frame.spaceControls.xSourceChoice.SetSelection(1)
        self.frame.spaceControls.handleSource("xSource", 1)
        self.panel.setView("Top")
        self.panel.snapshot(os.path.join(HERE, "room_azimuth.png"), 2)
        self.frame.spaceControls.xSourceChoice.SetSelection(0)
        self.frame.spaceControls.handleSource("xSource", 0)
        self.panel.setView("3D")

    def stop(self):
        event = wx.CommandEvent(wx.wxEVT_TOGGLEBUTTON)
        event.SetInt(0)
        self.controls.handleAudio(event)
        return 900

    def speakers(self):
        self.controls.changeOutputFormat({"output": "Speakers", "layout": "7.1.4", "order": 3,
                                          "customLayout": None, "customLayoutName": ""})
        return 1500

    def speakersShot(self):
        print("output:", self.audio.space["output"], self.audio.chnls, "channels")
        self.panel.snapshot(os.path.join(HERE, "room_speakers.png"), 2)

    def spaceWindow(self):
        self.frame.spaceControls.Show()
        self.frame.spaceControls.Raise()
        wx.CallLater(900, lambda: photograph("Space controls", "space_controls.png"))
        return 1600

    def settingsWindow(self):
        self.frame.spaceControls.Hide()
        self.controls.openSettings(None)
        wx.CallLater(900, lambda: photograph("Settings", "settings.png"))
        return 1600

    def done(self):
        self.controls.settingsWindow.Hide()
        self.frame.is_unsaved = False
        wx.CallLater(300, self.frame.Close)


Shots()
wx.GetApp().MainLoop()
