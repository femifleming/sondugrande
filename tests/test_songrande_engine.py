"""Songrande: the sound engine, rendered offline (no display, no audio device).

Every test builds a small project, renders it through the real engine into a
file and looks at the samples.

Run with python3 -m unittest discover -s tests
"""
import math
import os
import subprocess
import sys
import unittest

import numpy as np

from songrande_helpers import (ROOT, TMP, noiseSound, sineSound, roomPoints, stateWith, still,
                               renderState)
from songrande import ambi, render, space, wavio
from songrande.scene import Scene


def direction(az, el):
    return ambi.from_azel(math.radians(az), math.radians(el))


def roomAt(az, el, dist=1.0):
    """A room point (right, front, up) at an Ambisonic azimuth and elevation."""
    return tuple(space.ambi_to_room(direction(az, el) * dist))


def orbit(scene, seconds=4.0, radius=0.8, height=0.0, closed=False):
    """One turn round the listener in 'seconds', from the front to the left."""
    count = int(seconds / 0.025)
    a = np.linspace(0, 2 * np.pi, count, endpoint=False)
    pts = np.stack([-np.sin(a) * radius, np.cos(a) * radius, np.full_like(a, height)], axis=1)
    return scene.addTrajectory('free', points=roomPoints(pts), closed=closed)


def channelGains(samples, skip=0.3, rate=44100):
    """Gain of every channel relative to the first (W), by projection."""
    part = samples[:, int(skip * rate):]
    w = part[0]
    return part @ w / float(w @ w)


def maxStep(samples):
    return float(np.abs(np.diff(samples, axis=1)).max())


class EncodingTests(unittest.TestCase):
    def test_a_known_direction_gives_the_expected_channel_gains(self):
        for az, el in [(0, 0), (90, 0), (-45, 30), (135, -20), (10, 80)]:
            for order in (1, 3):
                with self.subTest(az=az, el=el, order=order):
                    state = stateWith(still(roomAt(az, el)))
                    samples, rate = renderState(state, dur=1.5, output="Ambisonics", order=order)
                    self.assertEqual(samples.shape[0], ambi.nch(order))
                    gains = channelGains(samples)
                    np.testing.assert_allclose(gains, ambi.sh(direction(az, el), order), atol=0.02)

    def test_seventh_order_has_sixty_four_channels_in_acn_order(self):
        state = stateWith(still(roomAt(60, 15)))
        samples, rate = renderState(state, dur=1.0, output="Ambisonics", order=7)
        self.assertEqual(samples.shape[0], 64)
        np.testing.assert_allclose(channelGains(samples), ambi.sh(direction(60, 15), 7), atol=0.02)

    def test_the_equaliser_and_compressor_leave_the_image_alone(self):
        state = stateWith(still(roomAt(-45, 30)))
        state["ControlPanel"]["eqamps"] = [6, -9, 3, -12]
        state["ControlPanel"]["compress"] = [-30, 8, 0.01, 0.1]
        state["ControlPanel"]["globalamp"] = 2.0
        samples, rate = renderState(state, dur=1.5, output="Ambisonics", order=3)
        np.testing.assert_allclose(channelGains(samples), ambi.sh(direction(-45, 30), 3), atol=0.02)

    def test_distance_changes_the_level_not_the_direction(self):
        levels = {}
        # towards a corner of the room, where there is space beyond the loudspeaker sphere
        for dist in (0.5, 1.0, 1.35):
            state = stateWith(still(roomAt(45, 0, dist)), doppler=0.0, air=0.0)
            state["ControlFrame"]["pitCheck"] = 0      # no transposition by the Y axis: the same grains everywhere
            samples, rate = renderState(state, dur=2.0, output="Ambisonics", order=1)
            np.testing.assert_allclose(channelGains(samples), ambi.sh(direction(45, 0), 1), atol=0.02)
            levels[dist] = float(np.sqrt(np.mean(samples[0, rate // 2:] ** 2)))
        self.assertGreater(levels[0.5], levels[1.0] * 1.3)
        self.assertGreater(levels[1.0], levels[1.35] * 1.1)
        # with the rolloff off the far sound is as loud as the near one
        state = stateWith(still(roomAt(45, 0, 1.35)), doppler=0.0, air=0.0, rolloff=0.0)
        state["ControlFrame"]["pitCheck"] = 0
        samples, rate = renderState(state, dur=2.0, output="Ambisonics", order=1)
        flat = float(np.sqrt(np.mean(samples[0, rate // 2:] ** 2)))
        self.assertGreater(flat, levels[1.35] * 1.15)

    def test_spread_and_the_middle_of_the_room(self):
        state = stateWith(still(roomAt(90, 0)), spread=1.0)
        samples, rate = renderState(state, dur=1.0, output="Ambisonics", order=3)
        gains = channelGains(samples)
        self.assertLess(np.abs(gains[1:]).max(), 0.02)        # all round: only the omni channel
        state = stateWith(still((0.0, 0.0, 0.0)))
        samples, rate = renderState(state, dur=1.0, output="Ambisonics", order=3)
        self.assertLess(np.abs(channelGains(samples)[1:]).max(), 0.02)
        self.assertTrue(np.isfinite(samples).all())

    def test_scene_turn(self):
        state = stateWith(still(roomAt(0, 0)), turn=90.0)
        samples, rate = renderState(state, dur=1.0, output="Ambisonics", order=1)
        np.testing.assert_allclose(channelGains(samples), ambi.sh(direction(90, 0), 1), atol=0.02)


class MovementTests(unittest.TestCase):
    def test_the_sound_follows_the_trajectory(self):
        state = stateWith(lambda scene: orbit(scene, 4.0))
        samples, rate = renderState(state, dur=4.0, output="Ambisonics", order=3)
        hop = rate // 4
        errors = []
        for f in range(samples.shape[1] // hop):
            vec, power = ambi.intensity_vector(samples[:4, f * hop:(f + 1) * hop])
            self.assertGreater(power, 1e-6)
            az = math.degrees(math.atan2(vec[1], vec[0]))
            expected = 360.0 * (f + 0.5) * hop / (4.0 * rate)
            errors.append(abs((az - expected + 180) % 360 - 180))
            self.assertLess(abs(vec[2]), 0.1)                 # it stays level
        self.assertLess(max(errors), 20.0, errors)
        self.assertLess(float(np.median(errors)), 8.0)

    def test_height_is_heard_as_elevation(self):
        def build(scene):
            a = np.linspace(0, np.pi, 120)                    # from in front, overhead, to behind
            pts = np.stack([np.zeros_like(a), np.cos(a) * 0.9, np.sin(a) * 0.9], axis=1)
            scene.addTrajectory('free', points=roomPoints(pts))
        samples, rate = renderState(stateWith(build), dur=3.0, output="Ambisonics", order=3)
        third = samples.shape[1] // 3
        first, _ = ambi.intensity_vector(samples[:4, rate // 4:third])
        middle, _ = ambi.intensity_vector(samples[:4, third + rate // 4:2 * third])
        last, _ = ambi.intensity_vector(samples[:4, 2 * third + rate // 4:])
        self.assertGreater(first[0], 0.5)       # in front
        self.assertGreater(middle[2], 0.8)      # overhead
        self.assertLess(last[0], -0.5)          # behind

    def test_no_clicks_and_no_nan_along_moving_trajectories(self):
        # a low sine, so that any step in a gain would stand out against its slope
        sound = sineSound("low.wav", freq=110.0)

        def build(scene):
            # an open path that jumps from its end back to its start, fast
            line = np.stack([np.linspace(-0.9, 0.9, 60), np.full(60, 0.4), np.linspace(-0.5, 0.9, 60)], axis=1)
            t = scene.addTrajectory('line', points=roomPoints(line))
            t.setStep(4)
            # straight through the listener's head
            through = np.stack([np.zeros(80), np.linspace(-0.8, 0.8, 80), np.zeros(80)], axis=1)
            t2 = scene.addTrajectory('line', points=roomPoints(through))
            t2.setDirection(2)
            t2.setStep(3)
            # a slow timer: the position steps instead of gliding
            t3 = orbit(scene, 1.0, 0.7, 0.3)
            t3.setTimeSpeed(120)
            t3.setStep(9)
            scene.addFxBall(1, center=roomPoints([(0, 0.4, 0.2)])[0], size=400)

        for name, values in [("glide", dict(glide=1.0)), ("stepped", dict(glide=0.0)),
                             ("scatter", dict(scatter=40.0, reverb=0.4, turnSpeed=45.0))]:
            for output, order in [("Ambisonics", 3), ("Binaural", 3), ("Speakers", 3)]:
                with self.subTest(case=name, output=output):
                    state = stateWith(build, sound=sound, **values)
                    state["ControlFrame"]["graindur"] = 300
                    samples, rate = renderState(state, dur=3.0, output=output, order=order)
                    self.assertTrue(np.isfinite(samples).all())
                    peak = float(np.abs(samples).max())
                    self.assertGreater(peak, 0.01)
                    self.assertLess(peak, 6.0)
                    # a 110 Hz sine of this peak moves at most peak * 2 pi f / rate per sample
                    # (0.016 * peak); overlapping grains, the FX ball's echoes and the fastest
                    # gain glide (3 ms) stay far below a tenth of the peak, a click does not
                    self.assertLess(maxStep(samples), 0.12 * peak, "%s %s" % (name, output))

    def test_doppler(self):
        sound = sineSound("tone.wav", freq=1000.0)

        def build(scene):
            # straight away from the listener: 0.8 radii in 2 s
            pts = np.stack([np.zeros(80), np.linspace(0.2, 1.0, 80), np.zeros(80)], axis=1)
            scene.addTrajectory('line', points=roomPoints(pts))

        def pitch(doppler, size):
            state = stateWith(build, sound=sound, doppler=doppler, roomSize=size, rolloff=0.0, air=0.0)
            state["ControlFrame"]["graindur"] = 400
            # grains at random times, so that their rate is not heard as a pitch of its own
            # (not the full deviation of 1: there pyo's granulator falls silent for whole seconds)
            state["ControlFrame"]["graindev"] = 0.6
            state["ControlFrame"]["rndpos"] = 0.3
            state["ControlFrame"]["pitCheck"] = 0       # the Y axis must not transpose here
            samples, rate = renderState(state, dur=2.0, output="Ambisonics", order=1)
            w = samples[0, rate // 4:int(1.9 * rate)]
            spec = np.abs(np.fft.rfft(w * np.hanning(len(w)), 1 << 18))
            freqs = np.fft.rfftfreq(1 << 18, 1.0 / rate)
            band = (freqs > 900) & (freqs < 1100)
            return float(np.sum(freqs[band] * spec[band] ** 2) / np.sum(spec[band] ** 2))

        still_pitch = pitch(0.0, 20.0)
        moving = pitch(1.0, 20.0)
        # 0.8 radii * 20 m in 2 s = 8 m/s away: 1000 Hz * (1 - 8 / 343) = 976.7 Hz
        self.assertAlmostEqual(still_pitch, 1000.0, delta=3.0)
        self.assertAlmostEqual(moving - still_pitch, -1000.0 * 8.0 / 343.0, delta=6.0)


class OutputTests(unittest.TestCase):
    def test_binaural_left_and_right(self):
        for az, louder in [(90, 0), (-90, 1)]:
            state = stateWith(still(roomAt(az, 0)))
            samples, rate = renderState(state, dur=1.5, output="Binaural")
            self.assertEqual(samples.shape[0], 2)
            level = np.sqrt(np.mean(samples[:, rate // 2:] ** 2, axis=1))
            self.assertGreater(level[louder], 1.8 * level[1 - louder])
        state = stateWith(still(roomAt(0, 0)))
        samples, rate = renderState(state, dur=1.5, output="Binaural")
        level = np.sqrt(np.mean(samples[:, rate // 2:] ** 2, axis=1))
        self.assertAlmostEqual(level[0] / level[1], 1.0, delta=0.05)

    def test_binaural_is_the_reference_decoder_of_the_bus(self):
        # the same seeded scene cannot be rendered twice (the grains are random), so compare levels:
        # the engine's convolutions against numpy's over the bus of another render
        from pyo.lib.hrtf import ImpulseResponseTables
        state = stateWith(still(roomAt(60, 20)))
        heard, rate = renderState(state, name="heard.wav", dur=2.0, output="Binaural")
        bus, rate = renderState(state, name="bus.wav", dur=2.0, output="Ambisonics", order=3)
        filters, signs = ambi.binaural_filters(3, ImpulseResponseTables().getTables(), 44100.0, taps=128)
        reference = ambi.binaural_render(filters, signs, bus)
        a = np.sqrt(np.mean(heard[:, rate // 2:] ** 2, axis=1))
        b = np.sqrt(np.mean(reference[:, rate // 2:] ** 2, axis=1))
        self.assertAlmostEqual(a[0] / a[1], b[0] / b[1], delta=0.12 * b[0] / b[1])
        self.assertAlmostEqual(a[0] / b[0], 1.0, delta=0.2)

    def test_stereo(self):
        state = stateWith(still(roomAt(90, 0)))
        samples, rate = renderState(state, dur=1.0, output="Stereo")
        level = np.sqrt(np.mean(samples[:, rate // 2:] ** 2, axis=1))
        self.assertEqual(samples.shape[0], 2)
        self.assertGreater(level[0], 20 * level[1])

    def test_loudspeakers(self):
        layout = ambi.LAYOUTS["Octagon"]
        for speaker in (0, 3, 6):
            az, el = layout[speaker]
            state = stateWith(still(roomAt(az, el)))
            samples, rate = renderState(state, dur=1.0, output="Speakers", layout="Octagon", order=3)
            self.assertEqual(samples.shape[0], 8)
            level = np.sqrt(np.mean(samples[:, rate // 2:] ** 2, axis=1))
            self.assertEqual(int(np.argmax(level)), speaker)
        state = stateWith(still(roomAt(45, 45)))
        samples, rate = renderState(state, dur=1.0, output="Speakers", layout="5.1.4", order=3)
        self.assertEqual(samples.shape[0], 10)
        level = np.sqrt(np.mean(samples[:, rate // 2:] ** 2, axis=1))
        self.assertEqual(level[3], 0.0)                    # the LFE gets nothing
        self.assertEqual(int(np.argmax(level)), 6)         # top front left

    def test_custom_layout(self):
        layout = [[0, 0], [120, 0], [-120, 0], [0, 90]]
        state = stateWith(still(roomAt(120, 0)), customLayout=layout, customLayoutName="tetra")
        samples, rate = renderState(state, dur=1.0, output="Speakers", order=2)
        self.assertEqual(samples.shape[0], 4)
        level = np.sqrt(np.mean(samples[:, rate // 2:] ** 2, axis=1))
        self.assertEqual(int(np.argmax(level)), 1)


class SceneSoundTests(unittest.TestCase):
    def test_grain_scatter_spreads_the_grains_round_the_trajectory(self):
        def directivity(samples, rate):
            vec, power = ambi.intensity_vector(samples[:4, rate // 2:])
            b = samples[:4, rate // 2:]
            return float(np.linalg.norm([np.mean(b[0] * b[3]), np.mean(b[0] * b[1]), np.mean(b[0] * b[2])]) / power)
        tight, rate = renderState(stateWith(still(roomAt(0, 0))), dur=2.0, output="Ambisonics", order=1)
        loose, rate = renderState(stateWith(still(roomAt(0, 0)), scatter=70.0), dur=2.0, output="Ambisonics", order=1)
        self.assertGreater(directivity(tight, rate), 0.97)
        self.assertLess(directivity(loose, rate), 0.9)
        # still in front on average
        vec, power = ambi.intensity_vector(loose[:4, rate // 2:])
        self.assertGreater(vec[0], 0.8)

    def test_fx_ball_sounds_from_where_it_is(self):
        ball_at = roomPoints([roomAt(-90, 0, 0.8)])[0]

        def inside(scene):
            # the stream stands in the ball, on the right; a harmonizer answers from the ball's centre
            scene.addTrajectory('line', points=[ball_at, (ball_at[0] + 1e-3, ball_at[1], ball_at[2])])
            scene.addFxBall(6, center=ball_at, size=200)

        def outside(scene):
            p = roomPoints([roomAt(90, 0, 0.8)])[0]
            scene.addTrajectory('line', points=[p, (p[0] + 1e-3, p[1], p[2])])
            scene.addFxBall(6, center=ball_at, size=200)

        dry, rate = renderState(stateWith(outside), dur=2.0, output="Ambisonics", order=1)
        wet, rate = renderState(stateWith(inside), dur=2.0, output="Ambisonics", order=1)
        # outside the ball: only the dry stream on the left
        np.testing.assert_allclose(channelGains(dry), ambi.sh(direction(90, 0), 1), atol=0.03)
        # inside: more sound than the dry stream alone, all of it from the right
        self.assertGreater(np.sqrt(np.mean(wet[0, rate // 2:] ** 2)), 1.15 * np.sqrt(np.mean(dry[0, rate // 2:] ** 2)))
        vec, power = ambi.intensity_vector(wet[:4, rate // 2:])
        self.assertLess(vec[1], -0.9)

    def test_every_effect_gives_out_sound_and_never_a_nan(self):
        ball_at = roomPoints([roomAt(-90, 0, 0.8)])[0]
        for fx in range(10):
            with self.subTest(fx=fx):
                def inside(scene, fx=fx):
                    scene.addTrajectory('line', points=[ball_at, (ball_at[0] + 1e-3, ball_at[1], ball_at[2])])
                    scene.addFxBall(fx, center=ball_at, size=200)
                samples, rate = renderState(stateWith(inside), dur=1.5, output="Ambisonics", order=1)
                self.assertTrue(np.isfinite(samples).all())
                self.assertGreater(float(np.abs(samples).max()), 0.01)
                self.assertLess(float(np.abs(samples).max()), 8.0)

    def test_harmonizer_ball_transposes(self):
        ball_at = roomPoints([roomAt(-90, 0, 0.8)])[0]

        def inside(scene):
            scene.addTrajectory('line', points=[ball_at, (ball_at[0] + 1e-3, ball_at[1], ball_at[2])])
            scene.addFxBall(6, center=ball_at, size=200)

        state = stateWith(inside, sound=sineSound("a440.wav", freq=440.0))
        state["ControlFrame"].update({"pitCheck": 0, "graindev": 0.6, "rndpos": 0.3})
        # an octave down, no feedback, the ball's sound at full level
        state["fxballs"]["0"]["controls"] = {"slider1": -12, "slider2": 0.0, "slider3": 1.0, "slider4": 0.0}
        samples, rate = renderState(state, dur=3.0, output="Ambisonics", order=1)
        w = samples[0, rate:]
        spec = np.abs(np.fft.rfft(w * np.hanning(len(w))))
        freqs = np.fft.rfftfreq(len(w), 1.0 / rate)

        def band(low, high):
            return float(np.sqrt(np.sum(spec[(freqs > low) & (freqs < high)] ** 2)))
        self.assertGreater(band(205, 235), 0.3 * band(420, 460))      # the octave below is there
        self.assertLess(band(280, 380), 0.05 * band(420, 460))        # and nothing in between

    def test_no_dropouts_at_the_walls(self):
        # the left and right walls are the start and the end of the sound: grains must
        # still fit there, with their random place as well
        for side in (-1.0, 1.0):
            with self.subTest(side=side):
                state = stateWith(still((side, 0.2, 0.0)))
                state["ControlFrame"].update({"rndpos": 0.6, "graindur": 400, "graindev": 0.5})
                samples, rate = renderState(state, dur=4.0, output="Ambisonics", order=1)
                hop = rate // 4
                levels = [float(np.sqrt(np.mean(samples[0, i * hop:(i + 1) * hop] ** 2)))
                          for i in range(1, samples.shape[1] // hop)]
                self.assertGreater(min(levels), 0.003, levels)

    def test_room_reverb_comes_from_all_round(self):
        dry, rate = renderState(stateWith(still(roomAt(0, 0))), dur=2.0, output="Ambisonics", order=1)
        wet, rate = renderState(stateWith(still(roomAt(0, 0)), reverb=1.0, reverbTime=0.9), dur=2.0,
                                output="Ambisonics", order=1)
        def side(samples):
            return float(np.sqrt(np.mean(samples[1, rate // 2:] ** 2)) / np.sqrt(np.mean(samples[0, rate // 2:] ** 2)))
        self.assertLess(side(dry), 0.03)
        self.assertGreater(side(wet), 0.08)
        self.assertTrue(np.isfinite(wet).all())

    def test_stereo_sound_file_and_sixteen_streams(self):
        sound = noiseSound("stereo.wav", channels=2)

        def build(scene):
            for i in range(16):
                a = 2 * np.pi * i / 16.0
                p = roomPoints([(math.sin(a) * 0.8, math.cos(a) * 0.8, 0.2 * math.sin(3 * a))])[0]
                scene.addTrajectory('line', points=[p, (p[0] + 1e-3, p[1], p[2])])

        samples, rate = renderState(stateWith(build, sound=sound), dur=1.5, output="Ambisonics", order=3)
        self.assertEqual(samples.shape[0], 16)
        self.assertTrue(np.isfinite(samples).all())
        gains = channelGains(samples)
        # sixteen sources evenly round the listener: first-order parts cancel
        self.assertLess(np.abs(gains[[1, 3]]).max(), 0.25)


class ProjectTests(unittest.TestCase):
    def test_save_and_load_with_three_dimensional_trajectories(self):
        def build(scene):
            scene.addTrajectory('spiral', center=(500, 500, 0), radius=250)
            t = orbit(scene, 2.0, 0.6, 0.4)
            t.setDirection(2)
            t.setWidth(40)
            scene.setMode('circle')
            scene.addTrajectory('circle', center=roomPoints([(0, 0.6, 0.8)])[0], radius=120, sphere=1.0,
                                basis=((1, 0, 0), (0, 0.8, 0.6), (0, -0.6, 0.8)))
            scene.addFxBall(0, center=(200, 300, 150), size=180)
        state = stateWith(build, scatter=15.0, reverb=0.3, output="Speakers", layout="Cube", order=2, xSource=1)
        path = os.path.join(TMP, "project.sgr")
        render.saveProject(state, path)
        loaded = render.loadProject(path)
        self.assertEqual(loaded["Space"]["layout"], "Cube")
        self.assertEqual(loaded["Space"]["xSource"], 1)
        scene = Scene()
        scene.setTrajectories(loaded)
        scene.setFxBalls(loaded["fxballs"])
        original = Scene()
        original.setTrajectories(state)
        original.setFxBalls(state["fxballs"])
        for a, b in zip(scene.getAllTrajectories(), original.getAllTrajectories()):
            self.assertEqual(a.getActive(), b.getActive())
            self.assertEqual(a.getType(), b.getType())
            self.assertEqual(a.getDirection(), b.getDirection())
            self.assertEqual(a.getWidth(), b.getWidth())
            self.assertEqual(a.sphere, b.sphere)
            np.testing.assert_allclose(np.array(a.getPoints()).reshape(-1, 3), np.array(b.getPoints()).reshape(-1, 3))
        heights = [p[2] for t in scene.getActiveTrajectories() for p in t.getPoints()]
        self.assertGreater(max(heights), 150)
        self.assertLess(min(heights), -150)
        self.assertEqual(scene.fxballs[0].getCenter(), (200.0, 300.0, 150.0))
        # and it plays: the loaded project renders to its own format
        samples, rate = wavio.read(render.render(path, os.path.join(TMP, "project.wav"), dur=1.0)[0])
        self.assertEqual(samples.shape[0], 8)
        self.assertGreater(float(np.abs(samples).max()), 0.01)

    def test_a_soundgrain_project_opens_on_the_floor(self):
        # SoundGrain's own empty project with one of its flat trajectories added
        state = render.loadProject(os.path.join(ROOT, "Resources", "new_soundgrain_file.sg"))
        self.assertNotIn("Space", state)
        size = state.get("SurfaceSize") or state["MainFrame"]["size"]
        w, h = float(size[0]), float(size[1])
        traj = state["Trajectories"]["0"]
        traj.update({"active": True, "type": "free", "closed": False,
                     "points": [[w * 0.25 + i, h * 0.1] for i in range(50)]})
        state["ControlPanel"]["sound"] = noiseSound()
        path = os.path.join(TMP, "old.sg")
        render.saveProject(state, path)
        scene, audio = render.buildEngine(render.loadProject(path), overrides={"output": "Ambisonics", "order": 1})
        try:
            pts = scene.getTrajectory(0).getPoints()
            self.assertAlmostEqual(pts[0][0], 250.0)
            self.assertAlmostEqual(pts[0][1], 100.0)
            self.assertEqual(pts[0][2], 0.0)
            self.assertEqual(audio.chnls, 4)
        finally:
            audio.shutdown()

    def test_the_new_project_file_is_the_empty_state(self):
        from songrande.constants import NEW_FILE
        state = render.loadProject(os.path.join(ROOT, "songrande", NEW_FILE))
        self.assertEqual(len(state["Trajectories"]), 16)
        self.assertEqual(state["Space"]["output"], "Binaural")
        self.assertFalse(any(t["active"] for t in state["Trajectories"].values()))

    def test_command_line_render(self):
        state = stateWith(lambda scene: orbit(scene, 2.0))
        project = os.path.join(TMP, "cli.sgr")
        render.saveProject(state, project)
        out = os.path.join(TMP, "cli.wav")
        result = subprocess.run([sys.executable, os.path.join(ROOT, "Songrande.py"), "--render", project, out,
                                 "--dur", "1.5", "--output", "Ambisonics", "--order", "2"],
                                capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stderr)
        samples, rate = wavio.read(out)
        self.assertEqual(samples.shape[0], 9)
        self.assertAlmostEqual(samples.shape[1] / float(rate), 1.5, delta=0.1)
        self.assertGreater(float(np.abs(samples).max()), 0.01)


if __name__ == '__main__':
    unittest.main()
