"""
Sondugrande - the self-test: start the real application, draw in the room with
the mouse handlers, play, record what comes out, check that the sound moves,
save the project, load it back, and quit.

    Sondugrande --selftest folder [--seconds 6] [--output Ambisonics] [--order 3]
                                [--layout Octagon] [--device "BlackHole 16ch"]
                                [--offline] [--keep]

With --offline (or SONDUGRANDE_AUDIO=offline) no audio device is needed: the
engine renders into the file instead of playing (this is what the build
machines run). The folder receives the recording, pictures of the room, the
saved project and report.json; the exit status is 0 if every check passed.

This file is part of Sondugrande, a derivative of SoundGrain (Olivier Belanger),
released under the GNU General Public License version 3 or later.
"""
import json
import math
import os
import sys
import time
import traceback


def parse(argv):
    import argparse
    parser = argparse.ArgumentParser(prog="Sondugrande --selftest")
    parser.add_argument("folder")
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--output", default="Ambisonics",
                        choices=["Binaural", "Stereo", "Ambisonics", "Speakers"])
    parser.add_argument("--order", type=int, default=3)
    parser.add_argument("--layout", default="Octagon")
    parser.add_argument("--device", default=None)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--keep", action="store_true", help="leave the window open at the end")
    return parser.parse_args(argv)


def makeSound(path, seconds=4.0, rate=44100):
    """A test sound with something everywhere along it: a noise band that
    sweeps, so every place in the file is audible and a little different."""
    import numpy as np
    from . import wavio
    rng = np.random.default_rng(7)
    n = int(seconds * rate)
    noise = rng.standard_normal(n)
    spec = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    spec *= 1.0 / np.maximum(freqs, 40.0) ** 0.5
    spec[freqs < 80] = 0
    spec[freqs > 9000] = 0
    base = np.fft.irfft(spec, n)
    t = np.arange(n) / rate
    tone = 0.3 * np.sin(2 * np.pi * (220 + 220 * t / seconds) * t)
    sound = base / np.abs(base).max() * 0.7 + tone
    sound *= 0.8 / np.abs(sound).max()
    wavio.write(path, sound, rate)
    return path


class SelfTest:
    def __init__(self, options):
        import wx
        from . import app as application
        from . import space
        self.wx = wx
        self.space = space
        self.options = options
        self.folder = os.path.abspath(options.folder)
        self.report = {"checks": {}, "errors": [], "options": vars(options)}
        self.app = application.SondugrandeApp(redirect=False)
        self.frame = self.app.frame
        self.frame.Show()
        self.panel = self.frame.panel
        self.controls = self.frame.controls
        self.audio = self.frame.sg_audio
        self.steps = [self.stepSound, self.stepFormat, self.stepDraw, self.stepPictures, self.stepSave,
                      self.stepPlay, self.stepAnalyse, self.stepReload, self.stepDone]
        self.code = 1
        wx.CallLater(600, self.next)

    def check(self, name, ok, detail=None):
        self.report["checks"][name] = {"ok": bool(ok), "detail": detail}
        print("%s  %s  %s" % ("PASS" if ok else "FAIL", name, "" if detail is None else detail))
        sys.stdout.flush()

    def next(self, delay=250):
        if not self.steps:
            return
        step = self.steps.pop(0)
        try:
            wait = step()
        except Exception:
            self.report["errors"].append(traceback.format_exc())
            traceback.print_exc()
            self.steps = [self.stepDone]
            wait = None
        if step is not self.stepDone:
            self.wx.CallLater(int(wait if wait else delay), self.next)

    # ------------------------------------------------------------------
    def stepSound(self):
        self.sound = makeSound(os.path.join(self.folder, "selftest_sound.wav"))
        self.controls.loadSound(self.sound)
        self.check("sound loaded", self.controls.sndPath == self.sound and self.controls.sndDur > 3.0,
                   "%.2f s" % self.controls.sndDur)

    def stepFormat(self):
        o = self.options
        self.controls.changeOutputFormat({"output": o.output, "order": o.order, "layout": o.layout,
                                          "customLayout": None, "customLayoutName": ""})
        got = self.audio.space["output"]
        self.report["output"] = got
        self.report["channels"] = self.audio.chnls
        self.check("output format", got == o.output, "%s, %d channels, order %d" % (got, self.audio.chnls, self.audio.order))
        return 500

    # -- the mouse, through the room's own handlers ---------------------
    def mouse(self, kind, x, y, cmd=False, shift=False, alt=False):
        wx = self.wx
        evt = wx.MouseEvent(kind)
        evt.SetPosition(wx.Point(int(round(x)), int(round(y))))
        evt.SetLeftDown(kind != wx.wxEVT_LEFT_UP)
        evt.SetControlDown(cmd)
        evt.SetShiftDown(shift)
        evt.SetAltDown(alt)
        handler = {wx.wxEVT_LEFT_DOWN: self.panel.MouseDown, wx.wxEVT_MOTION: self.panel.MouseMotion,
                   wx.wxEVT_LEFT_UP: self.panel.MouseUp}[kind]
        handler(evt)

    def drag(self, pixels, lift=None):
        """Press at the first pixel, move through the others, release.
        lift: (index, pixels up): at that point hold Cmd/Ctrl and move straight up."""
        wx = self.wx
        self.mouse(wx.wxEVT_LEFT_DOWN, *pixels[0])
        offset = 0.0
        for i, (x, y) in enumerate(pixels[1:], 1):
            if lift is not None and i == lift[0]:
                steps = 12
                px, py = pixels[i - 1][0], pixels[i - 1][1] - offset
                for s in range(1, steps + 1):
                    self.mouse(wx.wxEVT_MOTION, px, py - lift[1] * s / steps, cmd=True)
                offset += lift[1]
            self.mouse(wx.wxEVT_MOTION, x, y - offset)
        self.mouse(wx.wxEVT_LEFT_UP, pixels[-1][0], pixels[-1][1] - offset)

    def toPixels(self, room_points):
        import numpy as np
        xy, depth = self.panel.camera.project(np.asarray(room_points, dtype=float))
        return [(float(x), float(y)) for x, y in xy]

    def stepDraw(self):
        import numpy as np
        panel, space = self.panel, self.space
        w, h = panel.GetClientSize()
        panel.camera.setSize(w, h)
        before = len(panel.getActiveTrajectories())

        # 1. Top view, free-hand: once round the listener on the floor
        panel.setView("Top")
        panel.setDrawOn(0)
        self.controls.setType(0)
        a = np.linspace(0, 2 * np.pi, 140, endpoint=False)
        ring = np.stack([-np.sin(a) * 0.8, np.cos(a) * 0.8, np.zeros_like(a)], axis=1)   # from the front, to the left
        self.drag(self.toPixels(ring))
        t1 = panel.selected
        pts = np.array(t1.getPoints())
        room = space.canvas_to_room(pts)
        radius = np.hypot(room[:, 0], room[:, 1])
        self.check("free-hand on the floor", len(pts) > 100 and abs(np.median(radius) - 0.8) < 0.08
                   and np.abs(room[:, 2]).max() < 1e-6,
                   "%d points, median radius %.3f" % (len(pts), float(np.median(radius))))

        # 2. 3D view, a line drawn on the floor and pulled up half way (Cmd/Ctrl-drag)
        panel.setView("3D")
        self.controls.setType(3)
        line = np.stack([np.linspace(-0.7, 0.7, 30), np.full(30, -0.5), np.zeros(30)], axis=1)
        self.drag(self.toPixels(line), lift=(15, 90))
        t2 = panel.selected
        room2 = space.canvas_to_room(np.array(t2.getPoints()))
        self.check("pen pulled up while drawing", t2 is not t1 and room2[:, 2].max() > 0.15
                   and abs(room2[0, 2]) < 1e-6,
                   "%d points, rises to %.2f" % (len(room2), float(room2[:, 2].max())))

        # 3. a circle drawn on the sphere, overhead to the front right
        panel.setDrawOn(1)
        self.controls.setType(1)
        centre = np.array([0.45, 0.45, 0.77])
        centre = centre / np.linalg.norm(centre)
        edge = np.array([0.75, 0.45, 0.45])
        edge = edge / np.linalg.norm(edge)
        steps = [centre + (edge - centre) * k / 10.0 for k in range(11)]
        steps = [p / np.linalg.norm(p) for p in steps]
        self.drag(self.toPixels(steps))
        t3 = panel.selected
        room3 = space.canvas_to_room(np.array(t3.getPoints()))
        dist = np.linalg.norm(room3, axis=1)
        self.check("circle on the sphere", t3 is not t2 and t3.getType() == 'circle' and len(room3) > 20
                   and np.abs(dist - 1.0).max() < 0.03 and room3[:, 2].min() > 0.2,
                   "%d points, radius %.3f..%.3f" % (len(room3), float(dist.min()), float(dist.max())))

        # 4. Front view: pull a point of the first trajectory up (editing in a side view)
        panel.setDrawOn(0)
        panel.setView("Front")
        index = len(t1.getPoints()) // 4
        x, y = panel.toScreen(t1.getPoints()[index])
        self.drag([(x, y)] + [(x, y - 6 * k) for k in range(1, 11)])
        room1 = space.canvas_to_room(np.array(t1.getPoints()))
        self.check("point pulled up in the front view", room1[:, 2].max() > 0.1,
                   "highest point %.2f" % float(room1[:, 2].max()))

        # 5. move the second trajectory by its handle, and a twin of the first by the keyboard command
        panel.setView("Top")
        first = t2.getFirstPoint()
        x, y = panel.toScreen(first)
        self.drag([(x, y)] + [(x + 3 * k, y + 2 * k) for k in range(1, 11)])
        moved = t2.getFirstPoint()
        self.check("trajectory moved by its handle", abs(moved[0] - first[0]) > 5 and abs(moved[1] - first[1]) > 5,
                   "(%.0f, %.0f) -> (%.0f, %.0f)" % (first[0], first[1], moved[0], moved[1]))
        panel.setSelected(t3)
        twin = panel.mirrorSelected()
        self.check("mirrored twin", twin is not None and
                   abs(twin.getPoints()[0][0] - (space.CANVAS - t3.getPoints()[0][0])) < 1e-6)

        # 6. an FX ball (a delay) where the first trajectory passes, and some room
        panel.addFxBall(1)
        ball = list(panel.fxballs.values())[0]
        ball.move((500.0, 100.0, 0.0))
        ball.resize(260.0)
        panel.scene.placeBall(ball)
        self.frame.spaceControls.load(dict(self.audio.getSpace(), reverb=0.25, scatter=12.0))
        self.check("trajectories drawn", len(panel.getActiveTrajectories()) == before + 4,
                   "%d active" % len(panel.getActiveTrajectories()))
        panel.setView("3D")
        panel.setSelected(t1)
        self.t1 = t1
        # the checks below listen to the first trajectory alone, then to everything
        return 300

    def stepPictures(self):
        pictures = {}
        for view in ("3D", "Top", "Front", "Side"):
            self.panel.setView(view)
            path = os.path.join(self.folder, "room_%s.png" % view.lower())
            self.panel.snapshot(path)
            pictures[view] = os.path.getsize(path)
        self.panel.setView("3D")
        self.check("pictures of the room", all(size > 3000 for size in pictures.values()), pictures)

    def stepSave(self):
        self.project = os.path.join(self.folder, "selftest.sgr")
        self.frame.saveFile(self.project)
        self.saved = self.frame.getState()
        self.check("project saved", os.path.getsize(self.project) > 10000, self.project)

    def stepPlay(self):
        wx = self.wx
        seconds = self.options.seconds
        self.recording = os.path.join(self.folder, "selftest_out.wav")
        # solo the first trajectory (once round the listener in 'seconds'): its path is known
        self.others = [t for t in self.panel.getActiveTrajectories() if t is not self.t1]
        self.restore = [(t, t.getAttributes()) for t in self.others]
        for t in self.others:
            t.setActive(False)
        self.frame.spaceControls.load(dict(self.audio.getSpace(), reverb=0.0, scatter=0.0))
        count = len(self.t1.getPoints())
        # one revolution in the time there is: step a whole number of points every 25 ms
        self.t1.setTimeSpeed(25)
        self.t1.setStep(max(1, int(round(count / (seconds / 0.025)))))
        self.revolutions = self.t1.getStep() * (seconds / 0.025) / float(count)
        event = wx.CommandEvent(wx.wxEVT_TOGGLEBUTTON)
        event.SetInt(1)
        if self.audio.audioBackend != "portaudio":
            self.audio.server.recordOptions(dur=seconds, filename=self.recording, fileformat=0, sampletype=3)
            self.controls.handleAudio(event)      # renders the whole file, then comes back
            self.started = bool(self.controls.tog_audio.GetValue())
            return 100
        self.audio.server.recordOptions(fileformat=0, sampletype=3)
        self.controls.handleAudio(event)
        self.started = bool(self.audio.server.getIsStarted())
        self.audio.server.recstart(self.recording)
        self.wx.CallLater(int(seconds * 500), self.midway)
        return int(seconds * 1000) + 300

    def midway(self):
        # a picture of the real window while it plays
        try:
            self.panel.snapshot(os.path.join(self.folder, "room_playing.png"))
        except Exception:
            pass

    def stepAnalyse(self):
        import numpy as np
        from . import wavio, ambi
        wx = self.wx
        if self.audio.audioBackend == "portaudio":
            self.audio.server.recstop()
            event = wx.CommandEvent(wx.wxEVT_TOGGLEBUTTON)
            event.SetInt(0)
            self.controls.handleAudio(event)
        self.check("audio started", self.started)
        samples, rate = wavio.read(self.recording)
        channels = samples.shape[0]
        peak = float(np.abs(samples).max())
        rms = float(np.sqrt(np.mean(samples ** 2)))
        self.check("recording", channels == self.audio.chnls and samples.shape[1] > rate * self.options.seconds * 0.8,
                   "%d channels, %.2f s" % (channels, samples.shape[1] / float(rate)))
        self.check("not silent, no NaN, not clipped", rms > 1e-4 and np.isfinite(samples).all() and peak < 1.0,
                   "rms %.4f, peak %.3f" % (rms, peak))
        # the first trajectory goes once round the listener, from the front to the left:
        # the direction the sound comes from must follow it
        hop = int(rate * 0.25)
        frames = samples.shape[1] // hop
        track = []
        mode = self.audio.space["output"]
        if mode == "Speakers":
            dirs = ambi.layout_dirs(self.audio.getLayout())
            real = [i for i, d in enumerate(dirs) if d is not None]
            vectors = np.array([dirs[i] for i in real])
        for f in range(frames):
            seg = samples[:, f * hop:(f + 1) * hop]
            if mode == "Ambisonics":
                vec, power = ambi.intensity_vector(seg[:4])
                track.append(math.degrees(math.atan2(vec[1], vec[0])) if power > 1e-9 else None)
            elif mode == "Speakers":
                level = np.sqrt(np.mean(seg[real] ** 2, axis=1))
                vec = ambi.energy_vector(level, vectors)
                track.append(math.degrees(math.atan2(vec[1], vec[0])) if level.max() > 1e-5 else None)
            else:
                left, right = np.mean(seg[0] ** 2), np.mean(seg[1] ** 2)
                track.append(10 * math.log10((left + 1e-12) / (right + 1e-12)) if left + right > 1e-9 else None)
        self.report["track"] = track
        heard = [v for v in track if v is not None]
        if mode in ("Ambisonics", "Speakers"):
            # expected azimuth at the middle of each window
            errors = []
            for f, az in enumerate(track):
                if az is None:
                    continue
                expected = 360.0 * self.revolutions * (f + 0.5) / frames
                diff = (az - expected + 180.0) % 360.0 - 180.0
                errors.append(abs(diff))
            turned = float(np.ptp(np.unwrap(np.radians(heard)))) if heard else 0.0
            self.check("the sound moves where it was drawn",
                       len(errors) > frames * 0.6 and np.median(errors) < 25.0 and math.degrees(turned) > 200,
                       "median error %.1f degrees over %d windows, turned %.0f degrees"
                       % (float(np.median(errors)) if errors else -1, len(errors), math.degrees(turned)))
        else:
            spread = (max(heard) - min(heard)) if heard else 0.0
            half = len(heard) // 2
            first = float(np.mean(heard[1:half - 1])) if half > 3 else 0.0
            second = float(np.mean(heard[half + 1:-1])) if half > 3 else 0.0
            # front -> left -> back -> right: louder in the left ear first, in the right ear after
            self.check("the sound moves where it was drawn", spread > 6.0 and first > 2.0 and second < -2.0,
                       "left/right level: first half %+.1f dB, second half %+.1f dB" % (first, second))
        for t, attributes in self.restore:
            t.setAttributes(attributes)
        return 200

    def stepReload(self):
        import numpy as np
        self.frame.loadFile(self.project)
        self.wx.CallLater(400, self.compare)
        return 900

    def compare(self):
        import numpy as np
        try:
            now = self.frame.getState()
            same = True
            worst = 0.0
            for key, old in self.saved["Trajectories"].items():
                new = now["Trajectories"][key]
                if old["active"] != new["active"] or len(old["points"]) != len(new["points"]):
                    same = False
                    continue
                if old["points"]:
                    worst = max(worst, float(np.abs(np.array(old["points"], dtype=float)
                                                    - np.array(new["points"], dtype=float)).max()))
                for name in ("type", "step", "direction", "closed", "width", "sphere"):
                    if old.get(name) != new.get(name):
                        same = False
            space_same = all(self.saved["Space"].get(k) == now["Space"].get(k)
                             for k in ("output", "order", "reverb", "scatter", "roomSize"))
            balls = len(now["fxballs"]) == len(self.saved["fxballs"]) == 1
            self.check("project loaded back the same", same and worst < 1e-6 and space_same and balls,
                       "largest difference %.2g, %d balls" % (worst, len(now["fxballs"])))
        except Exception:
            self.report["errors"].append(traceback.format_exc())
            traceback.print_exc()

    def stepDone(self):
        ok = bool(self.report["checks"]) and all(c["ok"] for c in self.report["checks"].values()) \
            and not self.report["errors"] and len(self.report["checks"]) >= 14
        self.report["ok"] = ok
        with open(os.path.join(self.folder, "report.json"), "w") as f:
            json.dump(self.report, f, indent=1, default=str)
        print("SELFTEST %s (%d checks)" % ("PASSED" if ok else "FAILED", len(self.report["checks"])))
        sys.stdout.flush()
        self.code = 0 if ok else 1
        if self.options.keep:
            return
        self.frame.is_unsaved = False
        self.controls.sndPath = self.sound
        self.wx.CallLater(200, self.frame.Close)


def main(argv):
    options = parse(argv)
    os.makedirs(options.folder, exist_ok=True)
    prefs = os.path.join(os.path.abspath(options.folder), "selftest_prefs.txt")
    with open(prefs, "w") as f:
        f.write("audioDriver=%s\nmidiDriver=\nsamplePrecision=32-bit\nlastFilePath=%s\nlastAudioPath=%s\n"
                % (options.device or "", options.folder, options.folder))
    os.environ["SONDUGRANDE_PREFS"] = prefs
    if options.offline:
        os.environ["SONDUGRANDE_AUDIO"] = "offline"
    test = SelfTest(options)
    test.app.MainLoop()
    return test.code
