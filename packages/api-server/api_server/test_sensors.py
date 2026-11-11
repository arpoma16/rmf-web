import array
import asyncio
import struct
import threading
import unittest
import zlib
from types import SimpleNamespace

from api_server.sensors import (
    SensorCache,
    SensorTimeout,
    encode_png_gray,
    laser_scan_to_dict,
    occupancy_info,
    occupancy_to_png,
)


class FakeNode:
    """The three calls SensorCache makes on a ROS node."""

    def __init__(self):
        self.subscriptions: dict[str, tuple] = {}
        self.destroyed: list = []
        self.timer_destroyed = False

    def create_subscription(self, msg_type, topic, callback, qos):
        sub = SimpleNamespace(topic=topic, msg_type=msg_type, qos=qos)
        self.subscriptions[topic] = (sub, callback)
        return sub

    def destroy_subscription(self, sub):
        self.destroyed.append(sub.topic)
        self.subscriptions.pop(sub.topic, None)

    def create_timer(self, period, callback):
        return SimpleNamespace(period=period, callback=callback)

    def destroy_timer(self, timer):
        self.timer_destroyed = True

    def publish(self, topic, msg):
        self.subscriptions[topic][1](msg)


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def run(coro):
    return asyncio.run(coro)


class TestSensorCache(unittest.TestCase):
    def setUp(self):
        self.node = FakeNode()
        self.clock = FakeClock()
        self.cache = SensorCache(self.node, idle_ttl=30.0, clock=self.clock)

    def test_first_call_subscribes_and_waits_for_a_message(self):
        async def scenario():
            threading.Timer(0.05, lambda: self.node.publish("/a", "frame-1")).start()
            return await self.cache.get("/a", "Type", "qos", timeout=2.0)

        self.assertEqual("frame-1", run(scenario()))
        sub, _ = self.node.subscriptions["/a"]
        self.assertEqual(("Type", "qos"), (sub.msg_type, sub.qos))

    def test_a_fresh_cached_message_is_returned_without_waiting(self):
        async def scenario():
            threading.Timer(0.05, lambda: self.node.publish("/a", "frame-1")).start()
            await self.cache.get("/a", "Type", "qos", timeout=2.0)
            self.clock.now += 0.5
            return await self.cache.get("/a", "Type", "qos", timeout=0.1, max_age=1.0)

        self.assertEqual("frame-1", run(scenario()))

    def test_a_stale_message_is_not_returned(self):
        async def scenario():
            threading.Timer(0.05, lambda: self.node.publish("/a", "old")).start()
            await self.cache.get("/a", "Type", "qos", timeout=2.0)
            self.clock.now += 5.0  # older than max_age
            threading.Timer(0.05, lambda: self.node.publish("/a", "new")).start()
            return await self.cache.get("/a", "Type", "qos", timeout=2.0, max_age=1.0)

        self.assertEqual("new", run(scenario()))

    def test_a_stale_message_times_out_instead_of_being_returned(self):
        async def scenario():
            threading.Timer(0.05, lambda: self.node.publish("/a", "old")).start()
            await self.cache.get("/a", "Type", "qos", timeout=2.0)
            self.clock.now += 5.0
            await self.cache.get("/a", "Type", "qos", timeout=0.1, max_age=1.0)

        with self.assertRaises(SensorTimeout):
            run(scenario())

    def test_max_age_none_accepts_any_age(self):
        async def scenario():
            threading.Timer(0.05, lambda: self.node.publish("/map", "the-map")).start()
            await self.cache.get("/map", "Type", "qos", timeout=2.0, max_age=None)
            self.clock.now += 3600.0
            return await self.cache.get(
                "/map", "Type", "qos", timeout=0.1, max_age=None
            )

        self.assertEqual("the-map", run(scenario()))

    def test_timeout_without_any_message(self):
        with self.assertRaises(SensorTimeout):
            run(self.cache.get("/a", "Type", "qos", timeout=0.1))

    def test_one_message_wakes_every_waiter(self):
        async def scenario():
            threading.Timer(0.1, lambda: self.node.publish("/a", "frame")).start()
            return await asyncio.gather(
                self.cache.get("/a", "Type", "qos", timeout=2.0),
                self.cache.get("/a", "Type", "qos", timeout=2.0),
            )

        self.assertEqual(["frame", "frame"], run(scenario()))
        self.assertEqual(1, len(self.node.subscriptions))

    def test_a_timed_out_waiter_does_not_leak(self):
        with self.assertRaises(SensorTimeout):
            run(self.cache.get("/a", "Type", "qos", timeout=0.05))
        # a late message must not fail on the abandoned future
        self.node.publish("/a", "late")

    def test_purge_drops_only_idle_subscriptions(self):
        async def scenario():
            for topic in ("/a", "/b"):
                threading.Timer(0.05, lambda t=topic: self.node.publish(t, "x")).start()
                await self.cache.get(topic, "Type", "qos", timeout=2.0)
            self.clock.now += 20.0
            await self.cache.get(
                "/b", "Type", "qos", timeout=2.0, max_age=None
            )  # /b used again
            self.clock.now += 20.0  # /a idle 40 s, /b idle 20 s

        run(scenario())
        self.cache.purge_idle()
        self.assertEqual(["/a"], self.node.destroyed)
        self.assertEqual(["/b"], self.cache.topics())

    def test_a_message_after_the_purge_is_ignored(self):
        async def scenario():
            threading.Timer(0.05, lambda: self.node.publish("/a", "x")).start()
            await self.cache.get("/a", "Type", "qos", timeout=2.0)

        run(scenario())
        _, callback = self.node.subscriptions["/a"]
        self.clock.now += 60.0
        self.cache.purge_idle()
        callback("late")  # no entry any more: must not raise
        self.assertEqual([], self.cache.topics())

    def test_close_drops_everything(self):
        async def scenario():
            threading.Timer(0.05, lambda: self.node.publish("/a", "x")).start()
            await self.cache.get("/a", "Type", "qos", timeout=2.0)

        run(scenario())
        self.cache.close()
        self.assertEqual(["/a"], self.node.destroyed)
        self.assertTrue(self.node.timer_destroyed)


def _scan(ranges):
    return SimpleNamespace(
        header=SimpleNamespace(
            frame_id="bcr_bot_1/two_d_lidar", stamp=SimpleNamespace(sec=47, nanosec=5)
        ),
        angle_min=0.0,
        angle_max=6.28,
        angle_increment=0.0175,
        time_increment=0.0,
        scan_time=0.1,
        range_min=0.55,
        range_max=16.0,
        ranges=array.array("f", ranges),
    )


class TestLaserScan(unittest.TestCase):
    def test_fields_and_values(self):
        d = laser_scan_to_dict(_scan([1.5, 2.0]))
        self.assertEqual("bcr_bot_1/two_d_lidar", d["frame_id"])
        self.assertEqual({"sec": 47, "nanosec": 5}, d["stamp"])
        self.assertEqual(0.55, round(d["range_min"], 2))
        self.assertEqual([1.5, 2.0], d["ranges"])

    def test_returns_without_an_echo_become_null(self):
        d = laser_scan_to_dict(_scan([1.0, float("inf"), float("nan"), -float("inf")]))
        self.assertEqual([1.0, None, None, None], d["ranges"])


def _grid(width, height, cells, origin=(-4.858, -61.36)):
    return SimpleNamespace(
        header=SimpleNamespace(frame_id="map"),
        info=SimpleNamespace(
            resolution=0.05,
            width=width,
            height=height,
            origin=SimpleNamespace(
                position=SimpleNamespace(x=origin[0], y=origin[1]),
                orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
            ),
        ),
        data=array.array("b", cells),
    )


def _decode_png(png: bytes):
    """Minimal decoder for what encode_png_gray writes: (width, height, rows)."""
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, size = 8, b"", None
    while pos < len(png):
        (length,) = struct.unpack(">I", png[pos : pos + 4])
        tag = png[pos + 4 : pos + 8]
        data = png[pos + 8 : pos + 8 + length]
        (crc,) = struct.unpack(">I", png[pos + 8 + length : pos + 12 + length])
        assert crc == zlib.crc32(tag + data) & 0xFFFFFFFF, f"bad crc in {tag!r}"
        if tag == b"IHDR":
            size = struct.unpack(">II", data[:8])
            assert data[8:] == bytes([8, 0, 0, 0, 0]), "expected 8-bit grayscale"
        elif tag == b"IDAT":
            idat += data
        pos += 12 + length
    width, height = size
    raw = zlib.decompress(idat)
    stride = width + 1
    rows = []
    for y in range(height):
        assert raw[y * stride] == 0, "filter byte must be 0"
        rows.append(list(raw[y * stride + 1 : (y + 1) * stride]))
    return width, height, rows


class TestOccupancyGrid(unittest.TestCase):
    def test_info(self):
        info = occupancy_info(_grid(3, 2, [0] * 6))
        self.assertEqual("map", info["frame_id"])
        self.assertEqual(
            (3, 2, 0.05), (info["width"], info["height"], info["resolution"])
        )
        self.assertEqual({"x": -4.858, "y": -61.36, "yaw": 0.0}, info["origin"])

    def test_png_is_valid_and_has_the_map_orientation(self):
        # ROS stores row 0 at the bottom (smallest y); the image must have it at the bottom too.
        # cells, row by row from y = 0:  [free, occupied, unknown] then [occupied, free, free]
        png = occupancy_to_png(_grid(3, 2, [0, 100, -1, 100, 0, 0]))
        width, height, rows = _decode_png(png)
        self.assertEqual((3, 2), (width, height))
        self.assertEqual([0, 254, 254], rows[0])  # top = last map row (y = 1)
        self.assertEqual([254, 0, 205], rows[1])  # bottom = first map row (y = 0)

    def test_png_of_the_real_map_size(self):
        width, height = 1171, 1486  # factory_map_2 as loaded by the bcr_bot map_server
        png = occupancy_to_png(_grid(width, height, [0] * (width * height)))
        w, h, rows = _decode_png(png)
        self.assertEqual((width, height), (w, h))
        self.assertTrue(all(pixel == 254 for pixel in rows[0]))

    def test_intermediate_probabilities_are_gray(self):
        _, _, rows = _decode_png(occupancy_to_png(_grid(1, 1, [50])))
        self.assertEqual([[127]], rows)

    def test_encode_png_rejects_a_wrong_size(self):
        with self.assertRaises(ValueError):
            encode_png_gray(2, 2, b"\x00\x00\x00")


if __name__ == "__main__":
    unittest.main()
