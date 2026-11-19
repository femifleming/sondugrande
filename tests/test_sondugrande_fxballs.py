"""The FX balls after Pinkie Pie's Balloon Palace (Snow, Heat, Rpeg Ring Mod, Spectral Gate, Wind,
Fog) and Airwindows (Galactic, ToTape, Distance, Ensemble): each one sounds at both ends of both of
its controls without a NaN or a blow-up, and the ones whose effect can be measured do what they say.
The envelope window: the envelope is drawn dark on a white panel even when the system draws dark.

Run with python3 -m unittest discover -s tests
"""
import math
import os
import sys
import unittest

import numpy as np

from sondugrande_helpers import ROOT, noiseSound, roomPoints, stateWith, renderState
from sondugrande.constants import FX_BALL_TITLES, FX_BALL_SLIDER_1_INIT, FX_BALL_SLIDER_2_INIT

NEW = range(10, 20)


def ballPoint():
    return roomPoints([(0.0, 0.8, 0.0)])[0]


def render(fx, s1, s2, dur=2.0, sound=None):
    at = ballPoint()

    def inside(scene):
        scene.addTrajectory('line', points=[at, (at[0] + 1e-3, at[1], at[2])])
        scene.addFxBall(fx, center=at, size=200)
    state = stateWith(inside, sound=sound)
    state["fxballs"]["0"]["controls"] = {"slider1": s1, "slider2": s2, "slider3": 1.0, "slider4": 0.0}
    samples, rate = renderState(state, name="fx%d.wav" % fx, dur=dur, output="Ambisonics", order=1)
    return samples[0, rate // 2:], rate


def rms(x):
    return float(np.sqrt(np.mean(np.asarray(x, dtype=np.float64) ** 2)))


def brightness(x, rate):
    """the spectral centroid, Hz"""
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), 1.0 / rate)
    return float(np.sum(freqs * spec) / max(np.sum(spec), 1e-12))


class MoreBalls(unittest.TestCase):
    def test_titles_and_controls_for_all_twenty(self):
        for fx in range(20):
            self.assertIn(fx, FX_BALL_TITLES)
            for table in (FX_BALL_SLIDER_1_INIT, FX_BALL_SLIDER_2_INIT):
                name, lo, hi, init, log = table[fx]
                self.assertTrue(lo <= init <= hi, (fx, name))
                if log:
                    self.assertGreater(lo, 0, (fx, name))

    def test_every_new_ball_at_the_ends_of_its_controls(self):
        for fx in NEW:
            n1, lo1, hi1, _, _ = FX_BALL_SLIDER_1_INIT[fx]
            n2, lo2, hi2, _, _ = FX_BALL_SLIDER_2_INIT[fx]
            for s1, s2 in ((lo1, lo2), (hi1, hi2), (lo1, hi2), (hi1, lo2)):
                with self.subTest(ball=FX_BALL_TITLES[fx], s1=s1, s2=s2):
                    w, rate = render(fx, s1, s2, dur=1.5)
                    self.assertTrue(np.isfinite(w).all())
                    self.assertLess(float(np.abs(w).max()), 8.0)
                    self.assertGreater(float(np.abs(w).max()), 0.005)

    def test_distance_far_is_quieter_and_darker_than_near(self):
        near, rate = render(18, 0.0, 0.0)
        far, _ = render(18, 1.0, 1.0)
        self.assertLess(rms(far), rms(near))
        self.assertLess(brightness(far, rate), brightness(near, rate))

    def test_fog_darker_with_a_lower_cutoff(self):
        bright, rate = render(15, 0.6, 12000)
        dark, _ = render(15, 0.6, 300)
        self.assertLess(brightness(dark, rate), brightness(bright, rate))

    def test_spectral_gate_closes_as_the_threshold_rises(self):
        open_, _ = render(13, -90, 0.0)
        shut, _ = render(13, 0, 0.0)
        self.assertLess(rms(shut), rms(open_))


def _hasDisplay():
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


@unittest.skipUnless(_hasDisplay(), "needs a display")
class EnvelopeWindow(unittest.TestCase):
    """Draws the envelope editor into a bitmap through a drawing context whose background starts
    black (what a dark system appearance gives): the panel must come out white and the line dark."""

    @classmethod
    def setUpClass(cls):
        import wx
        cls.wx = wx
        cls.app = wx.App(False)

    def paint(self, cls):
        wx = self.wx
        frame = wx.Frame(None, size=(420, 260))
        graph = cls(frame, init=[(0.0, 0), (0.3, 1), (0.7, 1), (1.0, 0)], mode=1, size=(400, 220))
        graph.SetSize((400, 220))
        bmp = wx.Bitmap(400, 220)
        holder = {}

        def darkDC(win):
            dc = wx.MemoryDC(bmp)
            dc.SetBackground(wx.Brush(wx.BLACK))
            holder["dc"] = dc
            return dc
        if hasattr(graph, "_makeDC"):
            graph._makeDC = darkDC
        else:
            graph.dcref = darkDC
        graph.OnPaint(None)
        holder["dc"].SelectObject(wx.NullBitmap)
        img = np.frombuffer(bytes(bmp.ConvertToImage().GetData()), dtype=np.uint8).reshape(220, 400, 3)
        frame.Destroy()
        lum = img.mean(axis=2)
        return float((lum > 230).mean()), float((lum < 60).mean())

    def check(self, cls):
        white, dark = self.paint(cls)
        self.assertGreater(white, 0.6)        # the panel is white
        self.assertGreater(dark, 0.002)       # and the envelope (dark) is on it
        self.assertLess(dark, 0.2)

    def test_sondugrande_envelope_window(self):
        from sondugrande.MainFrame import EnvelopeGraph
        self.check(EnvelopeGraph)

    def test_soundgrain_envelope_window(self):
        sys.path.insert(0, ROOT)
        from Resources.MainFrame import EnvelopeGraph
        self.check(EnvelopeGraph)

    def test_without_the_fix_the_panel_goes_dark(self):
        # the reason for the fix: pyo's own Grapher, given the same dark context, draws on black
        from pyo.lib._wxwidgets import Grapher
        white, dark = self.paint(Grapher)
        self.assertLess(white, 0.3)


if __name__ == "__main__":
    unittest.main()
