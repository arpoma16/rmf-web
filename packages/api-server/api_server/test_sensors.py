import array
import asyncio
import struct
import threading
import unittest
import zlib
from types import SimpleNamespace

from api_server.sensors import (
    LEGACY_SENSORS,
    CameraSpec,
    FleetSensors,
    SensorCache,
    SensorTimeout,
    UnsupportedImageEncoding,
    encode_png_gray,
    image_to_png,
    laser_scan_to_dict,
    occupancy_info,
    occupancy_to_png,
    parse_fleet_sensors,
    parse_fleet_sensors_config,
    sensors_of,
    topic_of,
)


class FakeNode:
    """The calls SensorCache makes on a ROS node."""

    def __init__(self):
        self.subscriptions: dict[str, tuple] = {}
        self.destroyed: list = []
        self.timer_destroyed = False
        self.publishers: dict[str, int] = {}

    def count_publishers(self, topic):
        return self.publishers.get(topic, 0)

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
    """
    Minimal decoder for what encode_png writes: (width, height, rows). A row is the flat
    list of its bytes: one per pixel for grayscale, R, G, B per pixel for color.
    """
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, size, color_type = 8, b"", None, None
    while pos < len(png):
        (length,) = struct.unpack(">I", png[pos : pos + 4])
        tag = png[pos + 4 : pos + 8]
        data = png[pos + 8 : pos + 8 + length]
        (crc,) = struct.unpack(">I", png[pos + 8 + length : pos + 12 + length])
        assert crc == zlib.crc32(tag + data) & 0xFFFFFFFF, f"bad crc in {tag!r}"
        if tag == b"IHDR":
            size = struct.unpack(">II", data[:8])
            color_type = data[9]
            assert data[8] == 8 and data[10:] == bytes([0, 0, 0]), "expected 8-bit"
            assert color_type in (0, 2), "expected grayscale or RGB"
        elif tag == b"IDAT":
            idat += data
        pos += 12 + length
    width, height = size
    raw = zlib.decompress(idat)
    stride = width * (1 if color_type == 0 else 3) + 1
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


def _image(encoding, width, height, data, step=None):
    return SimpleNamespace(
        encoding=encoding,
        width=width,
        height=height,
        step=step if step is not None else len(data) // height,
        data=array.array("B", data),
    )


class TestRawImage(unittest.TestCase):
    def test_rgb8_keeps_the_colors_and_the_row_order(self):
        # the camera image has the top row first, like a PNG: it is not flipped
        msg = _image("rgb8", 2, 2, [255, 0, 0, 0, 255, 0, 0, 0, 255, 9, 9, 9])
        w, h, rows = _decode_png(image_to_png(msg))
        self.assertEqual((2, 2), (w, h))
        self.assertEqual([[255, 0, 0, 0, 255, 0], [0, 0, 255, 9, 9, 9]], rows)

    def test_bgr8_is_swapped_to_rgb(self):
        msg = _image("bgr8", 2, 1, [0, 0, 255, 0, 255, 0])  # red, green
        _, _, rows = _decode_png(image_to_png(msg))
        self.assertEqual([[255, 0, 0, 0, 255, 0]], rows)

    def test_mono8_is_grayscale(self):
        msg = _image("mono8", 3, 2, [1, 2, 3, 4, 5, 6])
        _, _, rows = _decode_png(image_to_png(msg))
        self.assertEqual([[1, 2, 3], [4, 5, 6]], rows)

    def test_the_padding_of_a_row_is_dropped(self):
        # 1 pixel wide, 4 bytes per row: 3 of color and 1 of padding
        msg = _image("rgb8", 1, 2, [10, 20, 30, 99, 40, 50, 60, 99], step=4)
        _, _, rows = _decode_png(image_to_png(msg))
        self.assertEqual([[10, 20, 30], [40, 50, 60]], rows)

    def test_the_size_of_the_simulation_camera(self):
        msg = _image("rgb8", 640, 480, [7] * (640 * 480 * 3))
        w, h, rows = _decode_png(image_to_png(msg))
        self.assertEqual((640, 480), (w, h))
        self.assertEqual([7] * (640 * 3), rows[0])

    def test_an_encoding_it_cannot_draw_is_refused_by_name(self):
        # the depth image of the kinect is 32FC1: not something to look at
        with self.assertRaises(UnsupportedImageEncoding):
            image_to_png(_image("32FC1", 1, 1, [0, 0, 0, 0]))

    def test_data_shorter_than_the_header_says_is_an_error_not_a_crash(self):
        msg = _image("rgb8", 2, 2, [0] * 6, step=6)
        with self.assertRaises(ValueError) as caught:
            image_to_png(msg)
        self.assertNotIsInstance(caught.exception, UnsupportedImageEncoding)


class TestHasPublisher(unittest.TestCase):
    def test_it_asks_the_ros_graph(self):
        node = FakeNode()
        node.publishers["/bcr_bot_1/scan"] = 1
        cache = SensorCache(node)
        self.assertTrue(cache.has_publisher("/bcr_bot_1/scan"))
        self.assertFalse(cache.has_publisher("/bcr_bot_1/front_camera/image_raw"))


FULL_BLOCK = {
    "cameras": [
        {"name": "front", "topic": "front_camera/image_raw", "kind": "raw"},
        {"name": "rear", "topic": "rear/image_raw/compressed", "kind": "compressed"},
    ],
    "lidar_2d": "scan",
    "lift_state": "lift_state",
    "map": "map",
}


class TestFleetSensorsConfig(unittest.TestCase):
    def test_a_full_block(self):
        self.assertEqual(
            FleetSensors(
                cameras=(
                    CameraSpec("front", "front_camera/image_raw", "raw"),
                    CameraSpec("rear", "rear/image_raw/compressed", "compressed"),
                ),
                lidar_2d="scan",
                lift_state="lift_state",
                map="map",
            ),
            parse_fleet_sensors(FULL_BLOCK),
        )

    def test_every_key_is_optional_and_what_is_not_declared_is_not_offered(self):
        self.assertEqual(FleetSensors(), parse_fleet_sensors({}))
        self.assertEqual(
            FleetSensors(lidar_2d="scan"), parse_fleet_sensors({"lidar_2d": "scan"})
        )

    def test_a_topic_cannot_leave_the_namespace_of_the_robot(self):
        for topic in ("/scan", "../other/scan", "a/../b", "scan/", "", "a b", "a//b"):
            with self.assertRaises(ValueError, msg=repr(topic)):
                parse_fleet_sensors({"lidar_2d": topic})
        with self.assertRaises(ValueError):
            parse_fleet_sensors({"lidar_2d": 3})

    def test_mistakes_are_named_with_their_place(self):
        bad = [
            ("sensors: expected a mapping", ["scan"]),
            ("unknown keys ['lidar']", {"lidar": "scan"}),
            (
                "cameras[0]: expected exactly name, topic and kind",
                {"cameras": [{"name": "a"}]},
            ),
            (
                "cameras[0].kind",
                {"cameras": [{"name": "a", "topic": "a", "kind": "jpeg"}]},
            ),
            (
                "cameras[0].name",
                {"cameras": [{"name": "a b", "topic": "a", "kind": "raw"}]},
            ),
            (
                "cameras[1].topic",
                {
                    "cameras": [
                        {"name": "a", "topic": "a", "kind": "raw"},
                        {"name": "b", "topic": "/b", "kind": "raw"},
                    ]
                },
            ),
            (
                "duplicate names",
                {
                    "cameras": [
                        {"name": "a", "topic": "a", "kind": "raw"},
                        {"name": "a", "topic": "b", "kind": "raw"},
                    ]
                },
            ),
        ]
        for expected, raw in bad:
            with self.assertRaises(ValueError) as caught:
                parse_fleet_sensors(raw)
            self.assertIn(expected, str(caught.exception))

    def test_the_configuration_is_by_fleet_and_none_stays_none(self):
        self.assertIsNone(parse_fleet_sensors_config(None))
        parsed = parse_fleet_sensors_config({"bcr_bot": FULL_BLOCK})
        self.assertEqual(["bcr_bot"], list(parsed))
        self.assertEqual("scan", parsed["bcr_bot"].lidar_2d)

    def test_a_mistake_names_the_fleet(self):
        with self.assertRaises(ValueError) as caught:
            parse_fleet_sensors_config({"bcr_bot": {"lidar_2d": "/scan"}})
        self.assertIn("fleet_sensors[bcr_bot].lidar_2d", str(caught.exception))
        with self.assertRaises(ValueError):
            parse_fleet_sensors_config(["bcr_bot"])

    def test_without_configuration_the_bcr_bot_defaults_apply_to_every_fleet(self):
        self.assertIs(LEGACY_SENSORS, sensors_of(None, "bcr_bot"))
        self.assertIs(LEGACY_SENSORS, sensors_of(None, "anything"))

    def test_with_configuration_a_fleet_offers_only_what_it_declares(self):
        config = parse_fleet_sensors_config({"bcr_bot": FULL_BLOCK})
        self.assertEqual("scan", sensors_of(config, "bcr_bot").lidar_2d)
        # TinyRobot has no block: it offers nothing, it does not inherit the bcr_bot defaults
        self.assertEqual(FleetSensors(), sensors_of(config, "tinyRobot"))

    def test_the_topic_is_in_the_namespace_of_the_robot(self):
        self.assertEqual("/bcr_bot_2/scan", topic_of("bcr_bot_2", "scan"))

    def test_app_config_validates_the_block_when_the_server_starts(self):
        from api_server.app_config import AppConfig
        from api_server.default_config import config

        ok = AppConfig(**{**config, "fleet_sensors": {"bcr_bot": FULL_BLOCK}})
        self.assertEqual("map", ok.fleet_sensors["bcr_bot"].map)
        self.assertIsNone(AppConfig(**config).fleet_sensors)
        with self.assertRaises(ValueError):
            AppConfig(**{**config, "fleet_sensors": {"bcr_bot": {"map": "/map"}}})


if __name__ == "__main__":
    unittest.main()
