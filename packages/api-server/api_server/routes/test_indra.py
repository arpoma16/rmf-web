import json
from unittest.mock import AsyncMock, patch

from std_msgs.msg import Bool

from api_server.app import app
from api_server.models import FleetState, FleetStateUpdate
from api_server.rmf_io import get_tasks_service
from api_server.test import AppFixture, make_task_state, try_until

from .robot_sensors import get_sensor_cache
from .test_robot_sensors import FakeCache

CATALOG = {
    "destinations": [
        {
            "id": "recogida_a",
            "name": "Recogida A",
            "kind": "pickup",
            "cart": {"yaw_deg": 90.0, "staging": "recogida_a_staging"},
        },
        {
            "id": "entrega_b",
            "name": "Entrega B",
            "kind": "dropoff",
            "cart": {"yaw_deg": 270.0, "staging": "entrega_b_staging"},
        },
    ]
}


def rmf_success() -> str:
    return '{"success": true, "state": %s}' % make_task_state().model_dump_json(
        exclude_none=True
    )


class TestIndraTransportRoute(AppFixture):
    def post(self, body: dict):
        return self.client.post("/indra/transport", content=json.dumps(body))

    def sent_to_rmf(self, mock) -> dict:
        return json.loads(mock.call_args[0][0])

    def test_without_a_robot_rmf_picks_one_and_gets_the_whole_delivery_as_one_task(self):
        with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch.object(
            get_tasks_service(), "call"
        ) as mock:
            mock.return_value = rmf_success()
            resp = self.post({"from": "recogida_a", "to": "entrega_b", "load": "box", "repeat": 2})
            self.assertEqual(200, resp.status_code, resp.content)
            sent = self.sent_to_rmf(mock)
            self.assertEqual("dispatch_task_request", sent["type"])
            request = sent["request"]
            self.assertEqual("compose", request["category"])
            self.assertEqual("bcr_bot", request["fleet_name"])
            self.assertEqual("admin", request["requester"])
            self.assertTrue(request["unix_millis_request_time"] > 0)
            self.assertEqual("transport_box", request["description"]["category"])
            steps = request["description"]["phases"][0]["activity"]["description"]["activities"]
            self.assertEqual(8, len(steps))
            self.assertIn("load=box", request["labels"])
            self.assertIn("repeat=2", request["labels"])
            self.assertIn("from=recogida_a", request["labels"])
            self.assertIn("to=entrega_b", request["labels"])
            # what the Pickup and Destination columns of the dashboard table read
            self.assertIn("pickup=recogida_a", request["labels"])
            self.assertIn("destination=entrega_b", request["labels"])

    def test_a_robot_task_carries_the_same_labels_because_it_saves_no_request(self):
        with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch.object(
            get_tasks_service(), "call"
        ) as mock:
            mock.return_value = rmf_success()
            resp = self.post({"from": "recogida_a", "to": "entrega_b", "robot": "bcr_bot_2", "repeat": 3})
            self.assertEqual(200, resp.status_code, resp.content)
            labels = self.sent_to_rmf(mock)["request"]["labels"]
            self.assertEqual(
                [
                    "transport",
                    "load=box",
                    "repeat=3",
                    "from=recogida_a",
                    "to=entrega_b",
                    "pickup=recogida_a",
                    "destination=entrega_b",
                ],
                labels,
            )

    def test_with_a_robot_the_task_goes_to_that_robot(self):
        with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch.object(
            get_tasks_service(), "call"
        ) as mock:
            mock.return_value = rmf_success()
            resp = self.post({"from": "recogida_a", "to": "entrega_b", "robot": "bcr_bot_2"})
            self.assertEqual(200, resp.status_code, resp.content)
            sent = self.sent_to_rmf(mock)
            self.assertEqual("robot_task_request", sent["type"])
            self.assertEqual("bcr_bot_2", sent["robot"])
            self.assertEqual("bcr_bot", sent["fleet"])
            self.assertEqual("transport_box", sent["request"]["description"]["category"])

    def test_the_load_defaults_to_a_box_and_the_repeat_to_one(self):
        with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch.object(
            get_tasks_service(), "call"
        ) as mock:
            mock.return_value = rmf_success()
            self.assertEqual(200, self.post({"from": "recogida_a", "to": "entrega_b"}).status_code)
            steps = self.sent_to_rmf(mock)["request"]["description"]["phases"][0]["activity"][
                "description"
            ]["activities"]
            self.assertEqual(4, len(steps))

    def test_a_request_that_cannot_work_is_a_400_with_a_code_and_never_reaches_rmf(self):
        cases = [
            ({"from": "nowhere", "to": "entrega_b"}, "unknown_destination"),
            ({"from": "entrega_b", "to": "entrega_b"}, "not_a_pickup"),
            ({"from": "recogida_a", "to": "recogida_a"}, "not_a_dropoff"),
            ({"from": "recogida_a", "to": "entrega_b", "load": "pallet"}, "invalid_load"),
            ({"from": "recogida_a", "to": "entrega_b", "repeat": 0}, "invalid_repeat"),
        ]
        with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch.object(
            get_tasks_service(), "call"
        ) as mock:
            for body, code in cases:
                with self.subTest(body=body):
                    resp = self.post(body)
                    self.assertEqual(400, resp.status_code, resp.content)
                    self.assertEqual(code, resp.json()["detail"]["error"])
                    self.assertTrue(resp.json()["detail"]["detail"])
            mock.assert_not_called()

    def test_a_malformed_body_is_a_422(self):
        with patch("api_server.routes.indra._catalog", return_value=CATALOG):
            self.assertEqual(422, self.post({"to": "entrega_b"}).status_code)

    def test_without_the_catalog_it_is_a_503(self):
        with patch("api_server.routes.indra._catalog", return_value=None):
            resp = self.post({"from": "recogida_a", "to": "entrega_b"})
            self.assertEqual(503, resp.status_code)
            self.assertEqual("catalog_unavailable", resp.json()["detail"]["error"])

    def test_when_rmf_refuses_the_task_the_answer_is_a_400(self):
        with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch.object(
            get_tasks_service(), "call"
        ) as mock:
            mock.return_value = (
                '{"success": false, "errors": [{"code": 1, "category": "x", "detail": "no fleet"}]}'
            )
            resp = self.post({"from": "recogida_a", "to": "entrega_b"})
            self.assertEqual(400, resp.status_code, resp.content)

    # ---- a robot that already carries a load cannot pick another one ----

    def test_a_named_robot_that_carries_a_load_is_refused_at_once_and_never_reaches_rmf(self):
        with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch(
            "api_server.routes.indra._lift_up", new=AsyncMock(return_value=True)
        ) as lift, patch.object(get_tasks_service(), "call") as mock:
            resp = self.post({"from": "recogida_a", "to": "entrega_b", "robot": "bcr_bot_1"})
            self.assertEqual(409, resp.status_code, resp.content)
            self.assertEqual("robot_carrying", resp.json()["detail"]["error"])
            self.assertIn("bcr_bot_1", resp.json()["detail"]["detail"])
            self.assertIn("/indra/deliver", resp.json()["detail"]["detail"])
            self.assertEqual("bcr_bot_1", lift.await_args.args[0])
            mock.assert_not_called()

    def test_only_a_known_load_blocks_an_unknown_one_does_not(self):
        for lift_up in (False, None):
            with self.subTest(lift_up=lift_up):
                with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch(
                    "api_server.routes.indra._lift_up", new=AsyncMock(return_value=lift_up)
                ), patch.object(get_tasks_service(), "call") as mock:
                    mock.return_value = rmf_success()
                    resp = self.post(
                        {"from": "recogida_a", "to": "entrega_b", "robot": "bcr_bot_1"}
                    )
                    self.assertEqual(200, resp.status_code, resp.content)

    def test_without_a_robot_nothing_asks_whether_it_carries_a_load(self):
        with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch(
            "api_server.routes.indra._lift_up", new=AsyncMock(return_value=True)
        ) as lift, patch.object(get_tasks_service(), "call") as mock:
            mock.return_value = rmf_success()
            resp = self.post({"from": "recogida_a", "to": "entrega_b"})
            self.assertEqual(200, resp.status_code, resp.content)
            lift.assert_not_awaited()

    def test_a_request_that_cannot_work_is_a_400_even_for_a_robot_that_carries_a_load(self):
        with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch(
            "api_server.routes.indra._lift_up", new=AsyncMock(return_value=True)
        ):
            resp = self.post({"from": "nowhere", "to": "entrega_b", "robot": "bcr_bot_1"})
            self.assertEqual(400, resp.status_code, resp.content)
            self.assertEqual("unknown_destination", resp.json()["detail"]["error"])


class TestIndraDeliverRoute(AppFixture):
    """`POST /indra/deliver`: put down the load a robot ALREADY carries."""

    def post(self, body: dict):
        return self.client.post("/indra/deliver", content=json.dumps(body))

    def sent_to_rmf(self, mock) -> dict:
        return json.loads(mock.call_args[0][0])

    def test_a_robot_that_carries_a_load_gets_one_task_that_puts_it_down(self):
        with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch(
            "api_server.routes.indra._lift_up", new=AsyncMock(return_value=True)
        ) as lift, patch.object(get_tasks_service(), "call") as mock:
            mock.return_value = rmf_success()
            resp = self.post({"to": "entrega_b", "robot": "bcr_bot_2"})
            self.assertEqual(200, resp.status_code, resp.content)
            self.assertEqual("bcr_bot_2", lift.await_args.args[0])
            sent = self.sent_to_rmf(mock)
            self.assertEqual("robot_task_request", sent["type"])
            self.assertEqual("bcr_bot_2", sent["robot"])
            self.assertEqual("bcr_bot", sent["fleet"])
            request = sent["request"]
            self.assertEqual("compose", request["category"])
            self.assertEqual("admin", request["requester"])
            self.assertEqual("deliver_box", request["description"]["category"])
            steps = request["description"]["phases"][0]["activity"]["description"]["activities"]
            self.assertEqual(
                ["go_to_place", "perform_action"], [step["category"] for step in steps]
            )
            self.assertEqual("entrega_b_staging", steps[0]["description"])
            self.assertEqual("drop_box", steps[1]["description"]["category"])
            self.assertEqual(
                ["deliver", "load=box", "to=entrega_b", "destination=entrega_b"], request["labels"]
            )

    def test_an_unknown_load_does_not_block_it(self):
        with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch(
            "api_server.routes.indra._lift_up", new=AsyncMock(return_value=None)
        ), patch.object(get_tasks_service(), "call") as mock:
            mock.return_value = rmf_success()
            self.assertEqual(200, self.post({"to": "entrega_b", "robot": "bcr_bot_2"}).status_code)

    def test_a_robot_known_to_carry_nothing_is_refused_at_once_and_never_reaches_rmf(self):
        with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch(
            "api_server.routes.indra._lift_up", new=AsyncMock(return_value=False)
        ), patch.object(get_tasks_service(), "call") as mock:
            resp = self.post({"to": "entrega_b", "robot": "bcr_bot_2"})
            self.assertEqual(409, resp.status_code, resp.content)
            self.assertEqual("robot_not_carrying", resp.json()["detail"]["error"])
            self.assertIn("bcr_bot_2", resp.json()["detail"]["detail"])
            mock.assert_not_called()

    def test_the_robot_is_required_because_the_load_is_on_that_robot(self):
        with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch.object(
            get_tasks_service(), "call"
        ) as mock:
            for body in ({"to": "entrega_b"}, {"to": "entrega_b", "robot": ""}):
                with self.subTest(body=body):
                    self.assertEqual(422, self.post(body).status_code)
            mock.assert_not_called()

    def test_only_a_dropoff_station_is_a_place_to_leave_a_load(self):
        cases = [
            ({"to": "nowhere", "robot": "bcr_bot_2"}, "unknown_destination"),
            ({"to": "recogida_a", "robot": "bcr_bot_2"}, "not_a_dropoff"),
            ({"to": "entrega_b", "robot": "bcr_bot_2", "load": "pallet"}, "invalid_load"),
        ]
        with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch(
            "api_server.routes.indra._lift_up", new=AsyncMock(return_value=True)
        ), patch.object(get_tasks_service(), "call") as mock:
            for body, code in cases:
                with self.subTest(body=body):
                    resp = self.post(body)
                    self.assertEqual(400, resp.status_code, resp.content)
                    self.assertEqual(code, resp.json()["detail"]["error"])
            mock.assert_not_called()

    def test_without_the_catalog_it_is_a_503(self):
        with patch("api_server.routes.indra._catalog", return_value=None):
            resp = self.post({"to": "entrega_b", "robot": "bcr_bot_2"})
            self.assertEqual(503, resp.status_code)
            self.assertEqual("catalog_unavailable", resp.json()["detail"]["error"])

    def test_when_rmf_refuses_the_task_the_answer_is_a_400(self):
        with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch(
            "api_server.routes.indra._lift_up", new=AsyncMock(return_value=True)
        ), patch.object(get_tasks_service(), "call") as mock:
            mock.return_value = (
                '{"success": false, "errors": [{"code": 1, "category": "x", "detail": "no robot"}]}'
            )
            resp = self.post({"to": "entrega_b", "robot": "bcr_bot_2"})
            self.assertEqual(400, resp.status_code, resp.content)


class TestIndraRoutesWithTheRealPlatform(AppFixture):
    """Nothing patches the platform here: the fleet and the state of each lift come in the way they do
    in the app (a seeded fleet and a cache of ROS messages), so the routes are tested against the real
    answer of `/robots/platform` and not against a stand-in of it."""

    def setUp(self):
        super().setUp()
        self.cache = FakeCache(
            {"/bcr_bot_1/lift_state": Bool(data=True), "/bcr_bot_2/lift_state": Bool(data=False)}
            # bcr_bot_3 publishes nothing: its load is unknown
        )
        app.dependency_overrides[get_sensor_cache] = lambda: self.cache
        self.addCleanup(app.dependency_overrides.pop, get_sensor_cache, None)
        robots = ("bcr_bot_1", "bcr_bot_2", "bcr_bot_3")
        fleet = FleetState(name="bcr_bot", robots={robot: {"name": robot} for robot in robots})
        with self.client.websocket_connect("/_internal") as ws:
            ws.send_text(
                FleetStateUpdate(type="fleet_state_update", data=fleet).model_dump_json()
            )
            try_until(
                lambda: self.client.get("/fleets"),
                lambda r: r.status_code == 200
                and any(set(f["robots"] or {}) == set(robots) for f in r.json()),
            )

    def post(self, path: str, body: dict):
        return self.client.post(path, content=json.dumps(body))

    def test_transport_refuses_the_robot_whose_platform_is_up_and_only_that_one(self):
        expected = {"bcr_bot_1": 409, "bcr_bot_2": 200, "bcr_bot_3": 200, "not_in_the_fleet": 200}
        for robot, status in expected.items():
            with self.subTest(robot=robot):
                with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch.object(
                    get_tasks_service(), "call"
                ) as mock:
                    mock.return_value = rmf_success()
                    resp = self.post(
                        "/indra/transport", {"from": "recogida_a", "to": "entrega_b", "robot": robot}
                    )
                    self.assertEqual(status, resp.status_code, resp.content)
                    if status == 409:
                        self.assertEqual("robot_carrying", resp.json()["detail"]["error"])
                        mock.assert_not_called()

    def test_deliver_refuses_the_robot_whose_platform_is_down_and_only_that_one(self):
        expected = {"bcr_bot_1": 200, "bcr_bot_2": 409, "bcr_bot_3": 200, "not_in_the_fleet": 200}
        for robot, status in expected.items():
            with self.subTest(robot=robot):
                with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch.object(
                    get_tasks_service(), "call"
                ) as mock:
                    mock.return_value = rmf_success()
                    resp = self.post("/indra/deliver", {"to": "entrega_b", "robot": robot})
                    self.assertEqual(status, resp.status_code, resp.content)
                    if status == 409:
                        self.assertEqual("robot_not_carrying", resp.json()["detail"]["error"])
                        mock.assert_not_called()
