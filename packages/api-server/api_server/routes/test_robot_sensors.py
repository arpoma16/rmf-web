import array

from nav_msgs.msg import OccupancyGrid
from sensor_msgs.msg import CompressedImage, Image, LaserScan
from std_msgs.msg import Bool

from api_server.app import app
from api_server.app_config import app_config
from api_server.models import FleetState, FleetStateUpdate
from api_server.sensors import SensorTimeout, parse_fleet_sensors_config
from api_server.test import AppFixture, try_until

from .robot_sensors import get_sensor_cache

JPEG = b"\xff\xd8\xff\xe0fake-jpeg\xff\xd9"
STEREO_TOPIC = "/bcr_bot_1/stereo_camera/right/image_raw/compressed"
FRONT_TOPIC = "/bcr_bot_1/front_camera/image_raw"


class FakeCache:
    """Stands in for SensorCache: a message per topic, no ROS."""

    def __init__(self, messages: dict):
        self.messages = messages
        self.calls: list[str] = []

    def has_publisher(self, topic):
        return topic in self.messages

    async def get(self, topic, msg_type, qos, *, timeout=3.0, max_age=1.0):
        self.calls.append(topic)
        msg = self.messages.get(topic)
        if msg is None:
            raise SensorTimeout(topic)
        return msg


def make_camera_frame(image_format="rgb8; jpeg compressed bgr8", data=JPEG):
    msg = CompressedImage()
    msg.format = image_format
    msg.data = array.array("B", data)
    return msg


def make_raw_frame(encoding="rgb8"):
    msg = Image()
    msg.width = 2
    msg.height = 1
    msg.encoding = encoding
    msg.step = 6 if encoding == "rgb8" else 8
    msg.data = array.array(
        "B", [255, 0, 0, 0, 255, 0] + ([0, 0] if encoding != "rgb8" else [])
    )
    return msg


def make_scan():
    msg = LaserScan()
    msg.header.frame_id = "bcr_bot_1/two_d_lidar"
    msg.angle_min = 0.0
    msg.angle_max = 6.28
    msg.angle_increment = 0.0175
    msg.range_min = 0.55
    msg.range_max = 16.0
    msg.ranges = [1.5, float("inf"), 2.0]
    return msg


def make_grid():
    msg = OccupancyGrid()
    msg.header.frame_id = "map"
    msg.info.resolution = 0.05
    msg.info.width = 3
    msg.info.height = 2
    msg.info.origin.position.x = -4.858
    msg.info.origin.position.y = -61.36
    msg.data = array.array("b", [0, 100, -1, 100, 0, 0])
    return msg


class TestRobotSensorsRoute(AppFixture):
    def setUp(self):
        super().setUp()
        self.cache = FakeCache(
            {
                STEREO_TOPIC: make_camera_frame(),
                "/bcr_bot_1/scan": make_scan(),
                "/bcr_bot_1/map": make_grid(),
            }
        )
        app.dependency_overrides[get_sensor_cache] = lambda: self.cache
        self.addCleanup(app.dependency_overrides.pop, get_sensor_cache, None)
        self.seed_robots("bcr_bot_1")

    def seed_robots(self, *robots: str):
        fleet = FleetState(
            name="bcr_bot", robots={robot: {"name": robot} for robot in robots}
        )
        with self.client.websocket_connect("/_internal") as ws:
            ws.send_text(
                FleetStateUpdate(
                    type="fleet_state_update", data=fleet
                ).model_dump_json()
            )
            try_until(
                lambda: self.client.get("/fleets"),
                # the exact set: the app is shared, so the previous test's robots may still be there
                lambda r: r.status_code == 200
                and any(set(f["robots"] or {}) == set(robots) for f in r.json()),
            )

    # ---- camera ----

    def test_a_compressed_camera_is_returned_as_it_was_published(self):
        resp = self.client.get("/robots/bcr_bot_1/camera")
        self.assertEqual(200, resp.status_code)
        self.assertEqual("image/jpeg", resp.headers["content-type"])
        self.assertEqual(JPEG, resp.content)
        self.assertEqual("no-store", resp.headers["cache-control"])
        self.assertEqual([STEREO_TOPIC], self.cache.calls)

    def test_a_raw_camera_is_returned_as_a_png(self):
        self.cache.messages = {FRONT_TOPIC: make_raw_frame()}
        resp = self.client.get("/robots/bcr_bot_1/camera")
        self.assertEqual(200, resp.status_code)
        self.assertEqual("image/png", resp.headers["content-type"])
        self.assertEqual(b"\x89PNG\r\n\x1a\n", resp.content[:8])
        self.assertEqual([FRONT_TOPIC], self.cache.calls)

    def test_the_front_camera_is_preferred_and_source_picks_another(self):
        self.cache.messages = {
            FRONT_TOPIC: make_raw_frame(),
            STEREO_TOPIC: make_camera_frame(),
        }
        self.assertEqual(
            "image/png",
            self.client.get("/robots/bcr_bot_1/camera").headers["content-type"],
        )
        resp = self.client.get("/robots/bcr_bot_1/camera?source=stereo_right")
        self.assertEqual("image/jpeg", resp.headers["content-type"])

    def test_a_robot_without_cameras_is_404_and_nothing_is_subscribed(self):
        self.cache.messages = {"/bcr_bot_1/scan": make_scan()}
        resp = self.client.get("/robots/bcr_bot_1/camera")
        self.assertEqual(404, resp.status_code)
        self.assertIn("has no camera", resp.json()["detail"])
        self.assertEqual([], self.cache.calls)

    def test_a_camera_that_does_not_exist_is_404(self):
        resp = self.client.get("/robots/bcr_bot_1/camera?source=back")
        self.assertEqual(404, resp.status_code)
        self.assertIn("named back", resp.json()["detail"])

    def test_a_raw_encoding_it_cannot_draw_is_415(self):
        self.cache.messages = {FRONT_TOPIC: make_raw_frame("32FC1")}
        self.assertEqual(415, self.client.get("/robots/bcr_bot_1/camera").status_code)

    def test_a_compressed_camera_with_an_unsupported_format(self):
        self.cache.messages[STEREO_TOPIC] = make_camera_frame("mono16; tiff")
        resp = self.client.get("/robots/bcr_bot_1/camera")
        self.assertEqual(415, resp.status_code)

    def test_a_robot_rmf_does_not_know_is_404_and_nothing_is_subscribed(self):
        for name in ("bcr_bot_9", "bad-name!"):
            resp = self.client.get(f"/robots/{name}/camera")
            self.assertEqual(404, resp.status_code, name)
        self.assertEqual([], self.cache.calls)

    def test_no_message_in_time_is_503(self):
        # the publisher exists (it is in the graph) but sends nothing
        self.cache.messages = {STEREO_TOPIC: None}
        self.cache.has_publisher = lambda topic: topic == STEREO_TOPIC
        resp = self.client.get("/robots/bcr_bot_1/camera")
        self.assertEqual(503, resp.status_code)
        self.assertIn(STEREO_TOPIC, resp.json()["detail"])

    # ---- lidar and map ----

    def test_lidar_is_json_and_an_echo_less_return_is_null(self):
        resp = self.client.get("/robots/bcr_bot_1/lidar")
        self.assertEqual(200, resp.status_code)
        body = resp.json()
        self.assertEqual("bcr_bot_1/two_d_lidar", body["frame_id"])
        self.assertEqual([1.5, None, 2.0], body["ranges"])
        self.assertAlmostEqual(0.55, body["range_min"], places=5)
        self.assertEqual(["/bcr_bot_1/scan"], self.cache.calls)

    def test_map_is_a_png(self):
        resp = self.client.get("/robots/bcr_bot_1/map")
        self.assertEqual(200, resp.status_code)
        self.assertEqual("image/png", resp.headers["content-type"])
        self.assertEqual(b"\x89PNG\r\n\x1a\n", resp.content[:8])
        self.assertEqual(["/bcr_bot_1/map"], self.cache.calls)

    def test_map_info(self):
        resp = self.client.get("/robots/bcr_bot_1/map/info")
        self.assertEqual(200, resp.status_code)
        info = resp.json()
        self.assertEqual((3, 2), (info["width"], info["height"]))
        self.assertAlmostEqual(0.05, info["resolution"], places=6)
        self.assertAlmostEqual(-61.36, info["origin"]["y"], places=5)

    # ---- what each robot offers, and the platform ----

    def test_capabilities_are_what_each_robot_publishes(self):
        self.seed_robots("bcr_bot_1", "bcr_bot_2")
        self.cache.messages = {
            FRONT_TOPIC: make_raw_frame(),
            STEREO_TOPIC: make_camera_frame(),
            "/bcr_bot_1/scan": make_scan(),
            "/bcr_bot_1/lift_state": Bool(data=False),
            "/bcr_bot_1/map": make_grid(),
            "/bcr_bot_2/scan": make_scan(),  # the second robot only has a lidar
        }
        resp = self.client.get("/robots/capabilities")
        self.assertEqual(200, resp.status_code)
        robots = resp.json()["robots"]
        self.assertEqual(["bcr_bot_1", "bcr_bot_2"], sorted(robots))
        self.assertEqual(
            [
                {"name": "front", "topic": FRONT_TOPIC, "kind": "raw"},
                {"name": "stereo_right", "topic": STEREO_TOPIC, "kind": "compressed"},
            ],
            robots["bcr_bot_1"]["cameras"],
        )
        self.assertEqual(
            (True, True, True),
            (
                robots["bcr_bot_1"]["lidar_2d"],
                robots["bcr_bot_1"]["lift"],
                robots["bcr_bot_1"]["map"],
            ),
        )
        # without configuration the bcr_bot defaults are declared: what the second robot does
        # not publish is reported as missing instead of silently absent
        self.assertEqual(
            {
                "fleet": "bcr_bot",
                "cameras": [],
                "lidar_2d": True,
                "lift": False,
                "map": False,
                "declared_but_missing": [
                    "front",
                    "stereo_right",
                    "stereo_left",
                    "lift",
                    "map",
                ],
            },
            robots["bcr_bot_2"],
        )
        self.assertEqual(
            [], self.cache.calls
        )  # asking what exists subscribes to nothing

    def test_platform_is_per_robot_and_null_without_a_lift(self):
        self.seed_robots("bcr_bot_1", "bcr_bot_2", "bcr_bot_3")
        self.cache.messages = {
            "/bcr_bot_1/lift_state": Bool(data=True),
            "/bcr_bot_2/lift_state": Bool(data=False),
            # bcr_bot_3 has no lift
        }
        resp = self.client.get("/robots/platform")
        self.assertEqual(200, resp.status_code)
        self.assertEqual(
            {
                "bcr_bot_1": {"lift_up": True},
                "bcr_bot_2": {"lift_up": False},
                "bcr_bot_3": {"lift_up": None},
            },
            resp.json()["robots"],
        )

    def test_platform_is_null_while_the_lift_has_not_reported(self):
        self.cache.messages = {"/bcr_bot_1/lift_state": None}
        self.cache.has_publisher = lambda topic: topic == "/bcr_bot_1/lift_state"
        resp = self.client.get("/robots/platform")
        self.assertEqual({"bcr_bot_1": {"lift_up": None}}, resp.json()["robots"])


class TestRobotSensorsFromTheFleetConfig(AppFixture):
    """The topics come from the `sensors` block of the fleet configuration."""

    BLOCK = {
        "cameras": [
            {"name": "mast", "topic": "mast_cam/image_raw", "kind": "raw"},
            {"name": "rear", "topic": "rear_cam/compressed", "kind": "compressed"},
        ],
        "lidar_2d": "lidar/scan",
        "lift_state": "platform/up",
        "map": "nav/map",
    }

    def setUp(self):
        super().setUp()
        previous = app_config.fleet_sensors
        app_config.fleet_sensors = parse_fleet_sensors_config({"bcr_bot": self.BLOCK})
        self.addCleanup(setattr, app_config, "fleet_sensors", previous)
        self.cache = FakeCache({})
        app.dependency_overrides[get_sensor_cache] = lambda: self.cache
        self.addCleanup(app.dependency_overrides.pop, get_sensor_cache, None)
        self.seed("bcr_bot", "bcr_bot_1")

    def seed(self, fleet_name: str, *robots: str):
        fleet = FleetState(
            name=fleet_name, robots={robot: {"name": robot} for robot in robots}
        )
        with self.client.websocket_connect("/_internal") as ws:
            ws.send_text(
                FleetStateUpdate(
                    type="fleet_state_update", data=fleet
                ).model_dump_json()
            )
            try_until(
                lambda: self.client.get("/fleets"),
                lambda r: r.status_code == 200
                and any(
                    f["name"] == fleet_name and set(f["robots"] or {}) == set(robots)
                    for f in r.json()
                ),
            )

    def test_the_declared_topics_are_used_not_the_defaults(self):
        self.cache.messages = {
            "/bcr_bot_1/mast_cam/image_raw": make_raw_frame(),
            "/bcr_bot_1/lidar/scan": make_scan(),
            "/bcr_bot_1/nav/map": make_grid(),
            "/bcr_bot_1/platform/up": Bool(data=True),
            # the old default topic is there too, but nobody declared it
            FRONT_TOPIC: make_raw_frame(),
        }
        caps = self.client.get("/robots/capabilities").json()["robots"]["bcr_bot_1"]
        self.assertEqual(
            [
                {
                    "name": "mast",
                    "topic": "/bcr_bot_1/mast_cam/image_raw",
                    "kind": "raw",
                }
            ],
            caps["cameras"],
        )
        self.assertEqual(
            (True, True, True), (caps["lidar_2d"], caps["lift"], caps["map"])
        )
        # the declared compressed camera has no publisher: reported, not hidden
        self.assertEqual(["rear"], caps["declared_but_missing"])
        self.assertEqual(
            "image/png",
            self.client.get("/robots/bcr_bot_1/camera").headers["content-type"],
        )
        self.assertEqual(200, self.client.get("/robots/bcr_bot_1/lidar").status_code)
        self.assertEqual(200, self.client.get("/robots/bcr_bot_1/map").status_code)
        # only this robot: the app is shared, other tests may have seeded other fleets
        self.assertEqual(
            {"lift_up": True},
            self.client.get("/robots/platform").json()["robots"]["bcr_bot_1"],
        )

    def test_a_declared_camera_that_nobody_publishes_is_missing_and_a_404(self):
        self.cache.messages = {"/bcr_bot_1/lidar/scan": make_scan()}
        caps = self.client.get("/robots/capabilities").json()["robots"]["bcr_bot_1"]
        self.assertEqual([], caps["cameras"])
        self.assertEqual(["mast", "rear", "lift", "map"], caps["declared_but_missing"])
        self.assertEqual(404, self.client.get("/robots/bcr_bot_1/camera").status_code)

    def test_a_fleet_without_a_block_offers_nothing(self):
        self.seed("tinyRobot", "tinyRobot1")
        self.cache.messages = {
            "/tinyRobot1/scan": make_scan()
        }  # published, not declared
        caps = self.client.get("/robots/capabilities").json()["robots"]["tinyRobot1"]
        self.assertEqual(
            {
                "fleet": "tinyRobot",
                "cameras": [],
                "lidar_2d": False,
                "lift": False,
                "map": False,
                "declared_but_missing": [],
            },
            caps,
        )
        for what in ("lidar", "map", "map/info"):
            resp = self.client.get(f"/robots/tinyRobot1/{what}")
            self.assertEqual(404, resp.status_code, what)
            self.assertIn("does not declare", resp.json()["detail"])
        self.assertEqual(
            {"lift_up": None},
            self.client.get("/robots/platform").json()["robots"]["tinyRobot1"],
        )
        self.assertEqual([], self.cache.calls)

    def test_a_fleet_that_does_not_declare_a_lift_has_a_null_platform(self):
        app_config.fleet_sensors = parse_fleet_sensors_config(
            {"bcr_bot": {"lidar_2d": "scan"}}
        )
        self.cache.messages = {"/bcr_bot_1/lift_state": Bool(data=True)}
        self.assertEqual(
            {"lift_up": None},
            self.client.get("/robots/platform").json()["robots"]["bcr_bot_1"],
        )
