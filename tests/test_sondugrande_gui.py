"""Sondugrande: the application itself (needs a display; no audio device).

Starts the real application in a process of its own and lets its self-test
draw in the room through the mouse handlers, play (rendering into a file in
place of an audio device), check that the sound moves the way it was drawn,
save the project and load it back.

Run with python3 -m unittest discover -s tests
"""
import json
import os
import subprocess
import sys
import unittest

from sondugrande_helpers import ROOT, TMP


def hasDisplay():
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


@unittest.skipUnless(hasDisplay(), "needs a display")
class ApplicationTests(unittest.TestCase):
    def run_selftest(self, name, *options):
        folder = os.path.join(TMP, name)
        result = subprocess.run([sys.executable, os.path.join(ROOT, "Sondugrande.py"), "--selftest", folder,
                                 "--offline", "--seconds", "4"] + list(options),
                                capture_output=True, text=True, timeout=300)
        report_path = os.path.join(folder, "report.json")
        self.assertTrue(os.path.isfile(report_path), result.stdout + result.stderr)
        with open(report_path) as f:
            report = json.load(f)
        failed = [name for name, check in report["checks"].items() if not check["ok"]]
        self.assertEqual(failed, [], result.stdout + result.stderr)
        self.assertEqual(report["errors"], [])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return folder, report

    def test_draw_play_save_load_ambisonics(self):
        folder, report = self.run_selftest("gui_ambisonics", "--output", "Ambisonics", "--order", "3")
        self.assertEqual(report["channels"], 16)
        for picture in ("room_3d.png", "room_top.png", "room_front.png", "room_side.png"):
            self.assertGreater(os.path.getsize(os.path.join(folder, picture)), 3000)

    def test_draw_play_save_load_binaural(self):
        folder, report = self.run_selftest("gui_binaural", "--output", "Binaural")
        self.assertEqual(report["channels"], 2)

    def test_draw_play_save_load_loudspeakers(self):
        folder, report = self.run_selftest("gui_speakers", "--output", "Speakers", "--layout", "7.1.4")
        self.assertEqual(report["channels"], 12)

    def test_version(self):
        result = subprocess.run([sys.executable, os.path.join(ROOT, "Sondugrande.py"), "--version"],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Sondugrande", result.stdout)
        self.assertIn("SoundGrain 6.1.0", result.stdout)


if __name__ == '__main__':
    unittest.main()
