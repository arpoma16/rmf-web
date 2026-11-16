import json
from unittest.mock import patch

from api_server.rmf_io import get_tasks_service
from api_server.test import AppFixture, make_task_state

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

    def test_a_robot_task_carries_the_same_labels_because_it_saves_no_request(self):
        with patch("api_server.routes.indra._catalog", return_value=CATALOG), patch.object(
            get_tasks_service(), "call"
        ) as mock:
            mock.return_value = rmf_success()
            resp = self.post({"from": "recogida_a", "to": "entrega_b", "robot": "bcr_bot_2", "repeat": 3})
            self.assertEqual(200, resp.status_code, resp.content)
            labels = self.sent_to_rmf(mock)["request"]["labels"]
            self.assertEqual(
                ["transport", "load=box", "repeat=3", "from=recogida_a", "to=entrega_b"], labels
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
