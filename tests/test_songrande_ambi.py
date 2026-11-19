"""Songrande: the Ambisonic conventions and decoders (no display, no audio device).

Run with python3 -m unittest discover -s tests
"""
import json
import math
import os
import unittest

import numpy as np

from songrande_helpers import TMP
from songrande import ambi


def direction(az, el):
    return ambi.from_azel(math.radians(az), math.radians(el))


class SphericalHarmonicsTests(unittest.TestCase):
    def test_channel_counts(self):
        self.assertEqual([ambi.nch(o) for o in range(1, 8)], [4, 9, 16, 25, 36, 49, 64])
        self.assertEqual(ambi.order_for(16), 3)
        self.assertEqual(ambi.order_for(63), 6)
        self.assertEqual(list(ambi.acn_orders(2)), [0, 1, 1, 1, 2, 2, 2, 2, 2])
        self.assertEqual(list(ambi.acn_degrees(2)), [0, -1, 0, 1, -2, -1, 0, 1, 2])

    def test_first_order_is_ambix_w_y_z_x(self):
        # ACN order: W, Y, Z, X. SN3D: a plane wave has W = 1 and reaches 1 on its axis
        np.testing.assert_allclose(ambi.sh(direction(0, 0), 1), [1, 0, 0, 1], atol=1e-12)     # front
        np.testing.assert_allclose(ambi.sh(direction(90, 0), 1), [1, 1, 0, 0], atol=1e-12)    # left
        np.testing.assert_allclose(ambi.sh(direction(-90, 0), 1), [1, -1, 0, 0], atol=1e-12)  # right
        np.testing.assert_allclose(ambi.sh(direction(0, 90), 1), [1, 0, 1, 0], atol=1e-12)    # up
        np.testing.assert_allclose(ambi.sh(direction(180, 0), 1), [1, 0, 0, -1], atol=1e-12)  # back

    def test_known_direction_gives_the_ambix_gains(self):
        # the closed forms of the AmbiX specification (Nachbar et al. 2011), second order
        for az, el in [(30, 20), (-110, 45), (75, -60), (160, 5)]:
            a, e = math.radians(az), math.radians(el)
            expected = [
                1.0,
                math.sin(a) * math.cos(e),
                math.sin(e),
                math.cos(a) * math.cos(e),
                math.sqrt(3) / 2 * math.sin(2 * a) * math.cos(e) ** 2,
                math.sqrt(3) / 2 * math.sin(a) * math.sin(2 * e),
                0.5 * (3 * math.sin(e) ** 2 - 1),
                math.sqrt(3) / 2 * math.cos(a) * math.sin(2 * e),
                math.sqrt(3) / 2 * math.cos(2 * a) * math.cos(e) ** 2,
            ]
            np.testing.assert_allclose(ambi.sh(direction(az, el), 2), expected, atol=1e-12)
        # third order, the sectorial pair: sqrt(5/8) cos^3(el) sin / cos (3 az)
        a, e = math.radians(40), math.radians(25)
        y = ambi.sh(direction(40, 25), 3)
        self.assertAlmostEqual(y[9], math.sqrt(5 / 8) * math.cos(e) ** 3 * math.sin(3 * a), places=12)
        self.assertAlmostEqual(y[15], math.sqrt(5 / 8) * math.cos(e) ** 3 * math.cos(3 * a), places=12)

    def test_sn3d_normalisation_and_orthogonality_up_to_seventh_order(self):
        dirs = ambi.fibonacci(20000)
        y = ambi.sh(dirs, 7)
        gram = y.T @ y / len(dirs)
        l = ambi.acn_orders(7)
        np.testing.assert_allclose(gram, np.diag(1.0 / (2 * l + 1)), atol=2e-4)

    def test_lower_orders_are_the_first_channels_of_higher_ones(self):
        d = direction(33, -12)
        np.testing.assert_allclose(ambi.sh(d, 7)[:16], ambi.sh(d, 3), atol=1e-12)

    def test_encode_on_the_sphere_inside_it_and_spread(self):
        d = direction(50, 10)
        np.testing.assert_allclose(ambi.encode(d, 3), ambi.sh(d, 3), atol=1e-12)
        # far away: the same direction (the distance model sets the level, not the encoder)
        np.testing.assert_allclose(ambi.encode(d * 1.6, 3), ambi.sh(d, 3), atol=1e-12)
        # near the listener the higher orders fade, and at the centre only the omni channel is left
        near = ambi.encode(d * 0.03, 3)
        self.assertLess(abs(near[1]), abs(ambi.sh(d, 3)[1]))
        centre = ambi.encode(np.zeros(3), 3)
        self.assertAlmostEqual(centre[0], 1.0)      # the distance model raises the level there, not the encoder
        np.testing.assert_allclose(centre[1:], 0, atol=1e-12)
        wide = ambi.encode(d, 3, spread=1.0)
        np.testing.assert_allclose(wide[1:], 0, atol=1e-12)
        self.assertAlmostEqual(wide[0], 2.0)        # a wide source is made up by half the lost energy (6 dB at 3rd order)
        half = ambi.encode(d, 3, spread=0.5)
        self.assertTrue(np.all(np.abs(half[1:4]) < np.abs(ambi.sh(d, 3)[1:4]) * half[0] + 1e-12))

    def test_max_re_weights(self):
        np.testing.assert_allclose(ambi.maxre(1), [1.0, math.cos(math.radians(137.9) / 2.51)], atol=1e-12)
        w = ambi.maxre(3)
        self.assertTrue(np.all(np.diff(w) < 0) and w[-1] > 0)

    def test_rotation_about_the_vertical(self):
        np.testing.assert_allclose(ambi.rotate_z(direction(0, 0), math.radians(90)), direction(90, 0), atol=1e-12)


class DecoderTests(unittest.TestCase):
    def test_every_layout_points_where_the_source_is(self):
        for name in ambi.LAYOUT_NAMES:
            if name == "Stereo":
                continue
            layout = ambi.LAYOUTS[name]
            matrix = ambi.allrad(layout, 3)
            dirs = ambi.layout_dirs(layout)
            real = [i for i, d in enumerate(dirs) if d is not None]
            vectors = np.array([dirs[i] for i in real])
            self.assertEqual(matrix.shape, (len(layout), 16))
            for i, d in enumerate(dirs):
                if d is None:
                    self.assertTrue(np.all(matrix[i] == 0), "%s: LFE gets no signal" % name)
            flat = bool(np.all(np.abs(vectors[:, 2]) < 1e-6))
            for i in real:
                # a source at a loudspeaker: the energy points there, and that loudspeaker is the loudest
                gains = matrix @ ambi.sh(dirs[i], 3)
                vec = ambi.energy_vector(gains[real], vectors)
                angle = math.degrees(math.acos(np.clip(vec @ dirs[i] / np.linalg.norm(vec), -1, 1)))
                self.assertLess(angle, 16.0, "%s speaker %d" % (name, i + 1))
                self.assertEqual(int(np.argmax(np.abs(gains))), i, "%s speaker %d" % (name, i + 1))
            # loudness about the same wherever the source is (on the horizon for flat layouts)
            probes = [direction(az, 0) for az in range(0, 360, 15)]
            if not flat:
                probes += [direction(az, 40) for az in range(0, 360, 30)]
            energy = [float(np.sum((matrix @ ambi.sh(p, 3)) ** 2)) for p in probes]
            self.assertLess(max(energy) / min(energy), 2.6, name)
            self.assertGreater(min(energy), 0.4, name)

    def test_decoders_exist_for_every_order(self):
        for order in range(1, 8):
            matrix = ambi.allrad(ambi.LAYOUTS["Octagon"], order)
            self.assertEqual(matrix.shape, (8, ambi.nch(order)))
            gains = matrix @ ambi.sh(direction(22.5, 0), order)
            self.assertEqual(int(np.argmax(gains)), 0)

    def test_stereo_pair(self):
        matrix = ambi.stereo_decoder(3)
        left = matrix @ ambi.sh(direction(90, 0), 3)
        front = matrix @ ambi.sh(direction(0, 0), 3)
        self.assertAlmostEqual(left[0], math.sqrt(2.0), places=12)
        self.assertAlmostEqual(left[1], 0.0, places=12)
        self.assertAlmostEqual(front[0], front[1], places=12)
        self.assertAlmostEqual(float(np.sum(front ** 2)), 1.0, places=12)

    def test_iem_layout_file(self):
        path = os.path.join(TMP, "layout.json")
        speakers = [{"Azimuth": 45.0, "Elevation": 0.0, "Radius": 1.0, "IsImaginary": False, "Channel": 2, "Gain": 1.0},
                    {"Azimuth": -45.0, "Elevation": 0.0, "Radius": 1.0, "IsImaginary": False, "Channel": 1, "Gain": 1.0},
                    {"Azimuth": 135.0, "Elevation": 10.0, "Radius": 1.0, "IsImaginary": False, "Channel": 4, "Gain": 1.0},
                    {"Azimuth": -135.0, "Elevation": 10.0, "Radius": 1.0, "IsImaginary": False, "Channel": 5, "Gain": 1.0},
                    {"Azimuth": 0.0, "Elevation": -90.0, "Radius": 1.0, "IsImaginary": True, "Channel": 6, "Gain": 0.0}]
        with open(path, "w") as f:
            json.dump({"Name": "test", "LoudspeakerLayout": {"Name": "test", "Loudspeakers": speakers}}, f)
        layout = ambi.load_iem_layout(path)
        self.assertEqual(layout, [(-45.0, 0.0), (45.0, 0.0), ambi.LFE, (135.0, 10.0), (-135.0, 10.0)])
        matrix = ambi.allrad(layout, 3)
        self.assertTrue(np.all(matrix[2] == 0))
        self.assertEqual(int(np.argmax(matrix @ ambi.sh(direction(45, 0), 3))), 1)

    def test_analysis_helpers(self):
        rng = np.random.default_rng(1)
        signal = rng.standard_normal(4000)
        d = direction(-70, 30)
        vec, power = ambi.intensity_vector(ambi.sh(d, 1)[:, None] * signal[None, :])
        np.testing.assert_allclose(vec, d, atol=1e-9)
        self.assertGreater(power, 0.5)


class BinauralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pyo.lib.hrtf import ImpulseResponseTables
        cls.tables = ImpulseResponseTables().getTables()
        cls.filters, cls.signs = ambi.binaural_filters(3, cls.tables, 44100.0, taps=128)

    def ears(self, az, el=0.0):
        gains = ambi.sh(direction(az, el), 3)
        left = (gains[:, None] * self.filters).sum(axis=0)
        right = ((gains * self.signs)[:, None] * self.filters).sum(axis=0)
        return left, right

    def test_shape_and_symmetry(self):
        self.assertEqual(self.filters.shape, (16, 128))
        self.assertTrue(np.isfinite(self.filters).all())
        left, right = self.ears(0)
        np.testing.assert_allclose(left, right, atol=1e-12)
        l1, r1 = self.ears(60, 20)
        l2, r2 = self.ears(-60, 20)
        np.testing.assert_allclose(l1, r2, atol=1e-12)
        np.testing.assert_allclose(r1, l2, atol=1e-12)

    def test_a_source_on_the_left_is_louder_and_earlier_in_the_left_ear(self):
        left, right = self.ears(90)
        level = 10 * math.log10(np.sum(left ** 2) / np.sum(right ** 2))
        self.assertGreater(level, 8.0)
        # below the crossover the ears keep their time difference (about 0.7 ms at the side)
        def lowpass(h):
            spec = np.fft.rfft(h, 2048)
            spec[np.fft.rfftfreq(2048, 1 / 44100.0) > 1200] = 0
            return np.fft.irfft(spec)
        a, b = lowpass(left), lowpass(right)
        lag = int(np.argmax(np.correlate(a, b, "full"))) - (len(a) - 1)
        self.assertTrue(-40 <= lag <= -20, lag)

    def test_colour_stays_close_to_the_measured_ears(self):
        dirs, irs = ambi.kemar_hrirs(self.tables)
        got = np.abs(np.fft.rfft(ambi.sh(dirs, 3) @ self.filters, 512, axis=1))
        want = np.abs(np.fft.rfft(irs, 512, axis=1))
        scale = math.sqrt(np.mean(want ** 2) / np.mean(got ** 2))
        freqs = np.fft.rfftfreq(512, 1 / 44100.0)
        band = (freqs > 300) & (freqs < 10000)
        error = 20 * np.log10((got[:, band] * scale + 1e-9) / (want[:, band] + 1e-9))
        self.assertLess(float(np.sqrt(np.mean(error ** 2))), 5.0)
        self.assertLess(abs(float(np.mean(error))), 2.5)

    def test_other_orders_and_rates(self):
        for order, rate in [(1, 44100.0), (2, 48000.0), (3, 96000.0)]:
            filters, signs = ambi.binaural_filters(order, self.tables, rate, taps=96)
            self.assertEqual(filters.shape[0], ambi.nch(order))
            self.assertTrue(np.isfinite(filters).all())
            self.assertEqual(len(signs), ambi.nch(order))

    def test_reference_renderer(self):
        rng = np.random.default_rng(5)
        signal = rng.standard_normal(2000)
        bus = ambi.sh(direction(-90, 0), 3)[:, None] * signal[None, :]
        out = ambi.binaural_render(self.filters, self.signs, bus)
        self.assertGreater(np.sum(out[1] ** 2), 4 * np.sum(out[0] ** 2))


if __name__ == '__main__':
    unittest.main()
