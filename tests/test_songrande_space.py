"""Songrande: the geometry of the room and the trajectories in it (no display, no audio).

Run with python3 -m unittest discover -s tests
"""
import math
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

from songrande_helpers import roomPoints
from songrande import space
from songrande.Trajectory import Trajectory, onSphere
from songrande.scene import Scene, Ball, legacyFactors


class CoordinateTests(unittest.TestCase):
    def test_canvas_room_and_ambisonic_frames(self):
        # the middle of the floor is the listener
        np.testing.assert_allclose(space.canvas_to_room((500, 500, 0)), (0, 0, 0))
        # SoundGrain's top edge is the front wall, its right edge the right wall
        np.testing.assert_allclose(space.canvas_to_room((500, 0, 0)), (0, 1, 0))
        np.testing.assert_allclose(space.canvas_to_room((1000, 500, 250)), (1, 0, 0.5))
        # Ambisonics: x front, y left, z up
        np.testing.assert_allclose(space.canvas_to_ambi((500, 0, 0)), (1, 0, 0))
        np.testing.assert_allclose(space.canvas_to_ambi((0, 500, 0)), (0, 1, 0))
        np.testing.assert_allclose(space.canvas_to_ambi((500, 500, 500)), (0, 0, 1))
        pts = np.random.default_rng(0).uniform(-1, 1, (20, 3))
        np.testing.assert_allclose(space.canvas_to_room(space.room_to_canvas(pts)), pts, atol=1e-12)
        np.testing.assert_allclose(space.ambi_to_room(space.room_to_ambi(pts)), pts, atol=1e-12)

    def test_azimuth_elevation_distance(self):
        az, el, dist = space.azel_dist((-1, 1, 0))
        self.assertAlmostEqual(az, 45.0)
        self.assertAlmostEqual(dist, math.sqrt(2))
        az, el, dist = space.azel_dist((0, 1, 1))
        self.assertAlmostEqual(el, 45.0)

    def test_the_floor_is_soundgrains_surface(self):
        # SoundGrain: x = pixel / width, y = 1 - pixel / height
        for cx, cy in [(0, 0), (250, 900), (1000, 500), (613, 77)]:
            x, y = space.grain_xy((cx, cy, 123.0), 0.3)
            self.assertAlmostEqual(x, cx / 1000.0)
            self.assertAlmostEqual(y, 1 - cy / 1000.0)

    def test_other_sources_for_x_and_y(self):
        front, right, back = (500, 100, 0), (900, 500, 0), (500, 900, 0)
        self.assertAlmostEqual(space.grain_xy(front, 0, x_source=1)[0], 0.0)
        self.assertAlmostEqual(space.grain_xy(right, 0, x_source=1)[0], 0.25)
        self.assertAlmostEqual(space.grain_xy(back, 0, x_source=1)[0], 0.5)
        self.assertAlmostEqual(space.grain_xy(front, 0.37, x_source=2)[0], 0.37)
        self.assertAlmostEqual(space.grain_xy((500, 500, 250), 0, x_source=3)[0], 0.75)
        self.assertAlmostEqual(space.grain_xy((500, 500, -500), 0, y_source=1)[1], 0.0)
        self.assertAlmostEqual(space.grain_xy((500, 500, 500), 0, y_source=3)[1], 1.0)
        near = space.grain_xy((500, 450, 0), 0, y_source=2)[1]
        far = space.grain_xy((500, 50, 0), 0, y_source=2)[1]
        self.assertLess(near, far)

    def test_distance_cues(self):
        gain1, delay1, cut1 = space.distance_cues(1.0, 5.0, 1.0, 0.5, 1.0)
        self.assertAlmostEqual(gain1, 1.0)
        self.assertAlmostEqual(delay1, 5.0 / 343.0)
        gain2, delay2, cut2 = space.distance_cues(1.5, 5.0, 1.0, 0.5, 1.0)
        self.assertAlmostEqual(gain2, 1 / 1.5)
        self.assertGreater(delay2, delay1)
        self.assertLess(cut2, cut1)
        self.assertAlmostEqual(space.distance_cues(0.5, 5.0, 1.0)[0], 2.0)
        self.assertAlmostEqual(space.distance_cues(0.0, 5.0, 1.0)[0], 4.0)       # never more than +12 dB
        self.assertAlmostEqual(space.distance_cues(1.7, 5.0, 0.0)[0], 1.0)       # rolloff off
        self.assertAlmostEqual(space.distance_cues(1.7, 5.0, 1.0, 0.5, 0.0)[1], 0.0)   # Doppler off

    def test_scatter_ring(self):
        p = np.array([0.6, -0.3, 0.2])
        ring = space.scatter_ring(p, math.radians(20), 4, turn=0.7)
        self.assertEqual(ring.shape, (4, 3))
        for q in ring:
            self.assertAlmostEqual(np.linalg.norm(q), np.linalg.norm(p))
            angle = math.degrees(math.acos(q @ p / (q @ q)))
            self.assertAlmostEqual(angle, 20.0, places=6)
        np.testing.assert_allclose(ring.mean(axis=0) / np.linalg.norm(ring.mean(axis=0)), p / np.linalg.norm(p), atol=1e-9)
        np.testing.assert_allclose(space.scatter_ring(p, 0.0, 4), np.repeat(p[None], 4, axis=0))


class CameraTests(unittest.TestCase):
    def test_a_pixel_goes_back_to_the_point_it_came_from(self):
        camera = space.Camera()
        camera.setSize(900, 700)
        rng = np.random.default_rng(2)
        for view in space.VIEWS:
            camera.setView(view)
            for p in rng.uniform(-1, 1, (25, 3)):
                xy, depth = camera.project(p)
                origin, direction = camera.ray(xy[0], xy[1])
                self.assertAlmostEqual(np.linalg.norm(direction), 1.0)
                # the point lies on the ray under its pixel
                t = (p - origin) @ direction
                np.testing.assert_allclose(origin + direction * t, p, atol=1e-6, err_msg=view)

    def test_views(self):
        camera = space.Camera()
        camera.setSize(800, 600)
        camera.setView("Top")
        front, _ = camera.project((0, 1, 0))
        right, _ = camera.project((1, 0, 0))
        self.assertLess(front[1], 300)      # the front wall is at the top, as in SoundGrain
        self.assertGreater(right[0], 400)
        camera.setView("Front")
        up, _ = camera.project((0, 0, 1))
        self.assertLess(up[1], 300)
        self.assertAlmostEqual(up[0], 400)
        camera.setView("Side")
        front, _ = camera.project((0, 1, 0))
        self.assertLess(front[0], 400)
        camera.setView("3D")
        near, dn = camera.project(camera.eye() * 0.2)
        far, df = camera.project(-camera.eye() * 0.2)
        self.assertLess(dn, df)
        self.assertGreater(camera.pixelsPerUnit(camera.eye() * 0.2), camera.pixelsPerUnit(-camera.eye() * 0.2))

    def test_pointer_on_the_floor_and_on_the_sphere(self):
        camera = space.Camera()
        camera.setSize(900, 700)
        for target in [(0.3, 0.6, 0.0), (-0.8, -0.2, 0.0)]:
            xy, _ = camera.project(target)
            origin, direction = camera.ray(*xy)
            np.testing.assert_allclose(space.ray_plane(origin, direction, (0, 0, 0), (0, 0, 1)), target, atol=1e-6)
        xy, _ = camera.project(camera.eye() / np.linalg.norm(camera.eye()))
        origin, direction = camera.ray(*xy)
        hit = space.ray_sphere(origin, direction, 1.0)
        self.assertAlmostEqual(np.linalg.norm(hit), 1.0)
        np.testing.assert_allclose(hit, camera.eye() / np.linalg.norm(camera.eye()), atol=1e-6)
        # a ray that misses slides round the outline instead of failing
        miss = space.ray_sphere(np.array([0.0, -5.0, 3.0]), np.array([0.0, 1.0, 0.0]), 1.0)
        self.assertAlmostEqual(np.linalg.norm(miss), 1.0)
        self.assertIsNone(space.ray_plane(origin, np.array([1.0, 0, 0]), (0, 0, 0), (0, 0, 1)))

    def test_state(self):
        camera = space.Camera()
        camera.orbit(40, -25)
        camera.dolly(3)
        camera.setView("Side")
        other = space.Camera()
        other.setState(camera.getState())
        self.assertEqual(other.getState(), camera.getState())


def makeTrajectory(points=None, kind='free'):
    owner = SimpleNamespace(audio=Mock())
    t = Trajectory(owner, 1)
    t._random.seed(123)
    t.resetWander()
    if points is not None:
        t.setType(kind)
        t.setPoints(points)
    return t


class TrajectoryTests(unittest.TestCase):
    def test_clock_walks_the_points_in_three_dimensions(self):
        points = [(10, 20, 0), (30, 40, 50), (50, 60, 100), (70, 80, 150)]
        t = makeTrajectory(points)
        seen = []
        for tick in range(6):
            t.clock()
            seen.append(t.circlePos)
        self.assertEqual(seen, [points[i] for i in (0, 1, 2, 3, 0, 1)])
        self.assertEqual(t.counter, 6)

    def test_step_freeze_and_phase(self):
        points = [(i, 2 * i, 3 * i) for i in range(10)]
        t = makeTrajectory(points)
        t.setStep(3)
        order = []
        for tick in range(5):
            t.clock()
            order.append(points.index(t.circlePos))
        self.assertEqual(order, [0, 3, 6, 9, 2])
        self.assertAlmostEqual(t.getPhase(), 2 / 9.0)
        t.setFreeze(True)
        t.clock()
        self.assertEqual(points.index(t.circlePos), 2)
        t.setFreeze(False)
        t.initCounter()
        t.clock()
        self.assertEqual(t.circlePos, points[0])

    def test_backward_and_back_and_forth(self):
        points = [(i, 0, i) for i in range(5)]
        t = makeTrajectory(points)
        t.setDirection(1)
        order = []
        for tick in range(7):
            t.clock()
            order.append(points.index(t.circlePos))
        self.assertEqual(order, [4, 3, 2, 1, 0, 4, 3])
        t = makeTrajectory(points)
        t.setDirection(2)
        order = []
        for tick in range(11):
            t.clock()
            order.append(points.index(t.circlePos))
        self.assertEqual(order, [0, 1, 2, 3, 4, 3, 2, 1, 0, 1, 2])

    def test_engine_is_told_about_speed_transposition_and_activity(self):
        t = makeTrajectory()
        t.setTimeSpeed(40)
        t.owner.audio.setMetroTime.assert_called_with(0, 0.04)
        t.setTranspo(1.5)
        t.owner.audio.setTranspo.assert_called_with(0, 1.5)
        t.setActive(True)
        t.owner.audio.setActive.assert_called_with(0, 1)

    def test_width_makes_a_tube_round_the_path(self):
        for direction in ((1, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 1), (0, 0, 1), (1, 2, 2)):
            with self.subTest(direction=direction):
                d = np.array(direction, dtype=float)
                d /= np.linalg.norm(d)
                points = [tuple(np.array([400.0, 400.0, 0.0]) + d * i) for i in range(40)]
                t = makeTrajectory(points)
                t.setWidth(60)
                reach = []
                up = []
                for tick in range(600):
                    centre = np.array(points[tick % len(points)])
                    t.clock()
                    offset = np.array(t.circlePos) - centre
                    self.assertAlmostEqual(float(offset @ d), 0.0, places=6)     # square to the path
                    self.assertLessEqual(np.linalg.norm(offset), 29 + 1e-6)      # inside the tube
                    reach.append(np.linalg.norm(offset))
                    up.append(abs(offset[2]) if abs(d[2]) < 0.99 else abs(offset[0]) + abs(offset[1]))
                self.assertGreater(max(reach), 10)
                self.assertGreater(max(up), 3)       # it really leaves the plane of a flat path

    def test_default_width_plays_the_points_themselves(self):
        points = [(10, 20, 5), (30, 40, 6), (50, 60, 7)]
        t = makeTrajectory(points)
        t.setStep(2)
        for index in (0, 2, 1, 0):
            t.clock()
            self.assertEqual(t.circlePos, points[index])

    def test_width_stays_in_the_room(self):
        points = [(2.0 + i, 3.0, 495.0) for i in range(30)]
        t = makeTrajectory(points)
        t.setWidth(200)
        for tick in range(300):
            t.clock()
            x, y, z = t.circlePos
            self.assertTrue(0 <= x <= 1000 and 0 <= y <= 1000 and -500 <= z <= 500)

    def test_edit_pulls_a_point_and_its_neighbours(self):
        points = [(100 + i, 300, 0) for i in range(100)]
        t = makeTrajectory(points)
        t.setEditionLevel(4)
        t.setInitPoints()
        t.editTraj(50, (0, 0, -80))          # the offset is subtracted: 80 up
        z = [p[2] for p in t.getPoints()]
        self.assertAlmostEqual(z[50], 80)
        self.assertTrue(0 < z[45] < z[48] < 80)
        self.assertTrue(0 < z[55] < z[52] < 80)
        self.assertEqual(z[10], 0)
        self.assertEqual(z[90], 0)
        self.assertEqual([p[:2] for p in t.getPoints()], [p[:2] for p in points])

    def test_fill_points_and_closing(self):
        t = makeTrajectory()
        t.setType('free')
        t.activateLp(False)
        for p in [(100, 100, 0), (110, 100, 10), (120, 100, 20), (130, 110, 30)]:
            t.addPoint(p)
        t.addFinalPoint((130, 120, 40), True)
        pts = t.getPoints()
        self.assertGreater(len(pts), 8)
        # the way back ends next to the first point
        self.assertLess(np.linalg.norm(np.array(pts[-1]) - np.array(pts[0])), 3.0)
        before = len(pts)
        t.fillPoints(True)
        self.assertGreater(len(t.getPoints()), before)

    def test_attributes_round_trip(self):
        t = makeTrajectory([(1, 2, 3), (4, 5, 6), (7, 8, 9)], 'free')
        t.setActive(True)
        t.setWidth(40)
        t.setDirection(2)
        t.setStep(3)
        saved = eval(str(t.getAttributes()))          # the undo stack does exactly this
        other = makeTrajectory()
        other.setAttributes(saved)
        self.assertEqual(other.getAttributes(), t.getAttributes())
        self.assertEqual(other.getPoints(), [(1, 2, 3), (4, 5, 6), (7, 8, 9)])

    def test_a_soundgrain_trajectory_lands_on_the_floor(self):
        # what SoundGrain 6.1 saves: pixels of an 800 x 500 window, no height
        old = {'width': 2, 'geometryTransformed': False, 'wanderSpeed': 1.0, 'wanderPeriodicity': 0.0,
               'closed': True, 'activeLp': True, 'editLevel': 2, 'timeSpeed': 25, 'amplitude': 1, 'step': 1,
               'type': 'circle', 'center': [400, 250], 'radius': 100, 'active': True, 'freeze': False,
               'circlePos': [300, 250], 'counter': 0, 'filterCut': 5000,
               'points': [[300, 250], [400, 150], [500, 250], [400, 350]]}
        t = makeTrajectory()
        t.setAttributes(old, 1000 / 800.0, 1000 / 500.0)
        self.assertEqual(t.getPoints(), [(375.0, 500.0, 0.0), (500.0, 300.0, 0.0), (625.0, 500.0, 0.0), (500.0, 700.0, 0.0)])
        self.assertEqual(t.getCenter(), (500.0, 500.0, 0.0))
        self.assertEqual(t.circlePos, (375.0, 500.0, 0.0))
        self.assertEqual(t.getDirection(), 0)


class SceneTests(unittest.TestCase):
    def test_circle_on_the_floor_and_in_a_wall(self):
        scene = Scene()
        t = scene.addTrajectory('circle', center=(500, 500, 100), radius=300)
        pts = np.array(t.getPoints())
        self.assertGreater(len(pts), 300)
        np.testing.assert_allclose(np.hypot(pts[:, 0] - 500, pts[:, 1] - 500), 300, atol=3.0)
        np.testing.assert_allclose(pts[:, 2], 100, atol=1e-6)
        self.assertTrue(t.closed)
        # a wall: left-right and up-down
        wall = ((1, 0, 0), (0, 0, -1), (0, 1, 0))
        t2 = scene.addTrajectory('circle', center=(500, 200, 0), radius=200, basis=wall)
        pts = np.array(t2.getPoints())
        np.testing.assert_allclose(pts[:, 1], 200, atol=1e-6)
        np.testing.assert_allclose(np.hypot(pts[:, 0] - 500, pts[:, 2]), 200, atol=3.0)

    def test_spiral_climbs_and_shapes_stay_in_the_room(self):
        scene = Scene()
        scene.setOscilPeriod(3)
        scene.setOscilScaling(1)
        t = scene.addTrajectory('spiral', center=(500, 500, 0), radius=200)
        pts = np.array(t.getPoints())
        self.assertLess(pts[0, 2], -150)
        self.assertGreater(pts[-1, 2], 150)
        self.assertTrue(np.all(np.diff(pts[:, 2]) >= -1.0))
        turned = np.unwrap(np.arctan2(pts[:, 1] - 500, pts[:, 0] - 500))
        self.assertAlmostEqual(abs(turned[-1] - turned[0]) / (2 * math.pi), 3.0, delta=0.15)
        # too big for the room: the radius is cut back
        big = scene.addTrajectory('circle', center=(900, 500, 0), radius=400)
        self.assertLessEqual(max(p[0] for p in big.getPoints()), 1000.0 + 1e-6)
        self.assertAlmostEqual(big.getRadius(), 100.0)

    def test_circle_wrapped_on_the_sphere(self):
        scene = Scene()
        centre = roomPoints([(0.0, 0.6, 0.8)])[0]
        t = scene.addTrajectory('circle', center=centre, radius=150, sphere=1.0,
                                basis=((1, 0, 0), (0, 0.8, 0.6), (0, -0.6, 0.8)))
        room = space.canvas_to_room(np.array(t.getPoints()))
        np.testing.assert_allclose(np.linalg.norm(room, axis=1), 1.0, atol=1e-6)
        self.assertAlmostEqual(np.linalg.norm(space.canvas_to_room(onSphere((700, 500, 0), 1.5))), 1.5)

    def test_drawing_with_the_pen(self):
        scene = Scene()
        scene.lowpass = False
        scene.setMode('free')
        scene.beginDraw((100, 100, 0))
        for i in range(1, 60):
            scene.drawTo((100 + 5 * i, 100 + 2 * i, 3 * i))
        t = scene.endDraw((400, 220, 180))
        self.assertIs(t, scene.selected)
        self.assertTrue(t.getActive())
        pts = np.array(t.getPoints())
        self.assertGreater(len(pts), 60)
        # as in SoundGrain the path ends at the last place the pen was dragged to
        self.assertAlmostEqual(pts[:, 2].max(), 177, delta=1e-6)
        # a click without a drag leaves nothing
        scene.beginDraw((10, 10, 0))
        self.assertIsNone(scene.endDraw((10, 10, 0)))
        self.assertEqual(len(scene.getActiveTrajectories()), 1)
        # a line into the air
        scene.setMode('line')
        scene.beginDraw((200, 800, 0))
        scene.drawTo((600, 800, 400))
        line = scene.endDraw((600, 800, 400))
        pts = np.array(line.getPoints())
        self.assertGreater(len(pts), 100)
        ratio = (pts[:, 2] - pts[0, 2]) / np.maximum(pts[:, 0] - pts[0, 0], 1e-9)
        np.testing.assert_allclose(ratio[5:], 1.0, atol=0.05)

    def test_moving_keeps_the_trajectory_in_the_room(self):
        scene = Scene()
        t = scene.addTrajectory('line', points=[(100 + i, 500, 0) for i in range(100)])
        t.setInitPoints()
        offset = scene.moveTrajectory(t, (300, 0, -100))       # 300 to the left asked for, 100 up
        self.assertEqual(offset, (100.0, 0.0, -100.0))
        self.assertEqual(t.getPoints()[0], (0.0, 500.0, 100.0))

    def test_transformations(self):
        scene = Scene()
        t = scene.addTrajectory('line', points=[(500 + i, 300, 0) for i in range(0, 200, 2)])
        self.assertTrue(scene.transform(t, 'lift', 120))
        self.assertTrue(all(abs(p[2] - 120) < 1e-9 for p in t.getPoints()))
        first, last = np.array(t.getPoints()[0]), np.array(t.getPoints()[-1])
        scene.transform(t, 'rotate', 90)
        a, b = np.array(t.getPoints()[0]), np.array(t.getPoints()[-1])
        self.assertAlmostEqual(np.linalg.norm(b - a), np.linalg.norm(last - first), places=6)
        self.assertAlmostEqual(abs((b - a)[1]), np.linalg.norm(last - first), places=6)   # now runs front to back
        scene.transform(t, 'tilty', 90)
        a, b = np.array(t.getPoints()[0]), np.array(t.getPoints()[-1])
        self.assertAlmostEqual(abs((b - a)[1]), np.linalg.norm(last - first), places=6)   # about its own axis: unchanged
        scene.transform(t, 'tiltx', 90)
        a, b = np.array(t.getPoints()[0]), np.array(t.getPoints()[-1])
        self.assertAlmostEqual(abs((b - a)[2]), np.linalg.norm(last - first), places=6)   # now it stands up
        scene.transform(t, 'flatten')
        self.assertLess(np.ptp([p[2] for p in t.getPoints()]), 1e-9)
        scene.transform(t, 'sphere', 1.0)
        room = space.canvas_to_room(np.array(t.getPoints()))
        np.testing.assert_allclose(np.linalg.norm(room, axis=1), 1.0, atol=1e-9)
        xs = [p[0] for p in t.getPoints()]
        scene.transform(t, 'horizontal')
        self.assertAlmostEqual(min(xs) + max(xs), min(p[0] for p in t.getPoints()) + max(p[0] for p in t.getPoints()))
        size = np.ptp(np.array(t.getPoints()), axis=0).max()
        scene.transform(t, 'scale', 0.5)
        self.assertAlmostEqual(np.ptp(np.array(t.getPoints()), axis=0).max(), size * 0.5, places=6)

    def test_duplicate_and_memory(self):
        scene = Scene()
        scene.audio = Mock()
        t = scene.addTrajectory('circle', center=(300, 300, 50), radius=100)
        t.setDirection(2)
        twin = scene.duplicateTrajectory(t)
        self.assertEqual(twin.getPoints(), t.getPoints())
        self.assertEqual(twin.getDirection(), 2)
        self.assertEqual(twin.getId(), 1)
        scene.selected = t
        scene.memorize()
        note = scene.addTrajFromMemory(0, 1.5, 0.25, 67)
        self.assertEqual(note.getId(), 2)
        scene.audio.setTranspo.assert_called_with(2, 1.5)
        # velocity sets how far to the front (SoundGrain's Y), the height is kept
        self.assertAlmostEqual(note.getFirstPoint()[1], 750.0, delta=1.0)
        self.assertAlmostEqual(note.getFirstPoint()[2], t.getFirstPoint()[2])
        scene.deleteMemorizedTraj(0)
        self.assertFalse(note.getActive())

    def test_clock_tells_the_engine_where_the_stream_is(self):
        scene = Scene()
        scene.audio = audio = Mock()
        t = scene.addTrajectory('line', points=[(250, 100, 300), (251, 100, 300)])
        ball = Ball(1, 0, center=(250, 100, 300), size=200)
        scene.fxballs[0] = ball
        scene.clock(0)
        audio.setXposition.assert_called_with(0, 0.25)
        audio.setYposition.assert_called_with(0, 0.9)
        audio.setSpatial.assert_called_with(0, (250.0, 100.0, 300.0))
        audio.setMixerChannelAmp.assert_called_with(0, 0, 1.0)
        scene.xSource, scene.ySource = 2, 1
        scene.clock(0)
        audio.setXposition.assert_called_with(0, 1.0)
        audio.setYposition.assert_called_with(0, 0.8)

    def test_fx_ball_is_a_sphere(self):
        ball = Ball(0, 0, center=(500, 500, 0), size=200)
        self.assertAlmostEqual(ball.getAmpValue((500, 500, 0)), 1.0)
        self.assertEqual(ball.getAmpValue((500, 500, 150)), 0.0)          # above it
        inside = ball.getAmpValue((500, 500, 50))
        self.assertTrue(0 < inside < 1)
        self.assertAlmostEqual(inside, ball.getAmpValue((550, 500, 0)))   # the same in every direction
        saved = ball.save()
        scene = Scene()
        again = scene.restoreFxBall(saved)
        self.assertEqual(again.save(), saved)
        # a SoundGrain ball (top-left corner in window pixels) lands on the floor
        old = {"fx": 2, "id": 3, "pos": [100, 100], "size": 64, "gradient": 30, "fader": 1.0,
               "controls": {"slider1": 0.5, "slider2": 0.5, "slider3": 1.0, "slider4": 0.5}}
        ball = scene.restoreFxBall(old, 1000 / 800.0, 1000 / 500.0)
        self.assertAlmostEqual(ball.getCenter()[2], 0.0)
        self.assertAlmostEqual(ball.getSize(), 64 * 1.625)

    def test_scene_state_and_legacy_factors(self):
        scene = Scene()
        scene.addTrajectory('spiral', center=(500, 500, 0), radius=200)
        scene.addFxBall(4, center=(100, 200, 300))
        state = scene.getState()
        other = Scene()
        other.setTrajectories(state)
        other.setFxBalls(state["fxballs"])
        self.assertEqual(other.getState(), state)
        self.assertEqual(legacyFactors({"Space": {}}), (1.0, 1.0))
        self.assertEqual(legacyFactors({"SurfaceSize": (800, 500)}), (1.25, 2.0))


if __name__ == '__main__':
    unittest.main()
