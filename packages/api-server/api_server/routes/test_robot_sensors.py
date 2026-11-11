import array

from nav_msgs.msg import OccupancyGrid
from sensor_msgs.msg import CompressedImage, LaserScan

from api_server.app import app
from api_server.models import FleetState, FleetStateUpdate
from api_server.sensors import SensorTimeout
from api_server.test import AppFixture, try_until

from .robot_sensors import get_sensor_cache

JPEG = b"\xff\xd8\xff\xe0fake-jpeg\xff\xd9"
CAMERA_TOPIC = "/bcr_bot_1/stereo_camera/right/image_raw/compressed"


class FakeCache:
    """Stands in for SensorCache: a message per topic, no ROS."""

    def __init__(self, messages: dict):
        self.messages = messages
        self.calls: list[str] = []

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
                CAMERA_TOPIC: make_camera_frame(),
                "/bcr_bot_1/scan": make_scan(),
                "/bcr_bot_1/map": make_grid(),
            }
        )
        app.dependency_overrides[get_sensor_cache] = lambda: self.cache
        self.addCleanup(app.dependency_overrides.pop, get_sensor_cache, None)
        self.seed_robot("bcr_bot_1")

    def seed_robot(self, robot: str):
        fleet = FleetState(name="bcr_bot", robots={robot: {"name": robot}})
        with self.client.websocket_connect("/_internal") as ws:
            ws.send_text(
                FleetStateUpdate(
                    type="fleet_state_update", data=fleet
                ).model_dump_json()
            )
            try_until(
                lambda: self.client.get("/fleets"),
                lambda r: r.status_code == 200
                and any(robot in (f["robots"] or {}) for f in r.json()),
            )

    def test_camera_returns_the_frame_as_it_was_published(self):
        resp = self.client.get("/robots/bcr_bot_1/camera")
        self.assertEqual(200, resp.status_code)
        self.assertEqual("image/jpeg", resp.headers["content-type"])
        self.assertEqual(JPEG, resp.content)
        self.assertEqual("no-store", resp.headers["cache-control"])
        self.assertEqual([CAMERA_TOPIC], self.cache.calls)

    def test_camera_with_an_unsupported_format(self):
        self.cache.messages[CAMERA_TOPIC] = make_camera_frame("mono16; tiff")
        resp = self.client.get("/robots/bcr_bot_1/camera")
        self.assertEqual(415, resp.status_code)

    def test_a_robot_rmf_does_not_know_is_404_and_nothing_is_subscribed(self):
        for name in ("bcr_bot_9", "bad-name!"):
            resp = self.client.get(f"/robots/{name}/camera")
            self.assertEqual(404, resp.status_code, name)
        self.assertEqual([], self.cache.calls)

    def test_no_message_in_time_is_503(self):
        del self.cache.messages[CAMERA_TOPIC]
        resp = self.client.get("/robots/bcr_bot_1/camera")
        self.assertEqual(503, resp.status_code)
        self.assertIn(CAMERA_TOPIC, resp.json()["detail"])

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
