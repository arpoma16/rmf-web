"""The transport task of the Indra factory, built from the destinations catalog (pure, no RMF)."""
import math
import unittest

from api_server.indra_transport import (
    MAX_REPEAT,
    TransportError,
    build_deliver_description,
    build_description,
)

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
        {"id": "cargador_1", "name": "Cargador 1", "kind": "charger", "cart": None},
    ]
}


def activities(description):
    return description["phases"][0]["activity"]["description"]["activities"]


def action(category, station):
    return {
        "category": "perform_action",
        "description": {
            "category": category,
            "description": {"station": station},
            "unix_millis_action_duration_estimate": 60000,
            "use_tool_sink": False,
        },
    }


class TestBuildDescription(unittest.TestCase):
    def test_a_box_delivery_goes_to_the_staging_acts_there_and_does_the_same_at_the_drop(self):
        description = build_description(CATALOG, "recogida_a", "entrega_b", "box", 1)
        self.assertEqual("transport_box", description["category"])
        self.assertEqual(
            [
                {"category": "go_to_place", "description": "recogida_a_staging"},
                action("pick_box", "recogida_a"),
                {"category": "go_to_place", "description": "entrega_b_staging"},
                action("drop_box", "entrega_b"),
            ],
            activities(description),
        )

    def test_a_delivery_has_one_phase_so_it_is_one_task(self):
        description = build_description(CATALOG, "recogida_a", "entrega_b", "box", 3)
        self.assertEqual(1, len(description["phases"]))
        self.assertEqual("sequence", description["phases"][0]["activity"]["category"])

    def test_repeat_chains_whole_cycles_never_two_picks_in_a_row(self):
        steps = activities(build_description(CATALOG, "recogida_a", "entrega_b", "box", 3))
        self.assertEqual(12, len(steps))
        kinds = [
            s["description"]["category"] for s in steps if s["category"] == "perform_action"
        ]
        self.assertEqual(["pick_box", "drop_box"] * 3, kinds)

    def test_a_cart_delivery_keeps_the_orientation_the_contract_asks_for(self):
        description = build_description(CATALOG, "recogida_a", "entrega_b", "cart", 1)
        self.assertEqual("transport_cart", description["category"])
        steps = activities(description)
        self.assertEqual(
            {
                "category": "go_to_place",
                "description": {
                    "waypoint": "recogida_a_staging",
                    "orientation": math.radians(90.0),
                },
            },
            steps[0],
        )
        self.assertEqual(action("pick_cart", "recogida_a"), steps[1])
        self.assertAlmostEqual(
            math.radians(270.0), steps[2]["description"]["orientation"]
        )
        self.assertEqual(action("drop_cart", "entrega_b"), steps[3])

    def test_a_request_that_cannot_work_is_refused_with_a_code_and_a_reason(self):
        cases = [
            (("nowhere", "entrega_b", "box", 1), "unknown_destination"),
            (("recogida_a", "nowhere", "box", 1), "unknown_destination"),
            (("entrega_b", "entrega_b", "box", 1), "not_a_pickup"),
            (("recogida_a", "recogida_a", "box", 1), "not_a_dropoff"),
            (("cargador_1", "entrega_b", "box", 1), "not_a_pickup"),
            (("recogida_a", "entrega_b", "pallet", 1), "invalid_load"),
            (("recogida_a", "entrega_b", "box", 0), "invalid_repeat"),
            (("recogida_a", "entrega_b", "box", MAX_REPEAT + 1), "invalid_repeat"),
        ]
        for args, code in cases:
            with self.subTest(args=args):
                with self.assertRaises(TransportError) as error:
                    build_description(CATALOG, *args)
                self.assertEqual(code, error.exception.code)
                self.assertTrue(str(error.exception))

    def test_a_pickup_without_a_staging_is_refused(self):
        catalog = {
            "destinations": [
                dict(CATALOG["destinations"][0], cart=None),
                CATALOG["destinations"][1],
            ]
        }
        with self.assertRaises(TransportError) as error:
            build_description(catalog, "recogida_a", "entrega_b", "box", 1)
        self.assertEqual("not_a_station", error.exception.code)

    def test_without_a_catalog_it_says_so(self):
        with self.assertRaises(TransportError) as error:
            build_description(None, "recogida_a", "entrega_b", "box", 1)
        self.assertEqual("catalog_unavailable", error.exception.code)

    def test_the_largest_repeat_is_allowed(self):
        steps = activities(
            build_description(CATALOG, "recogida_a", "entrega_b", "box", MAX_REPEAT)
        )
        self.assertEqual(4 * MAX_REPEAT, len(steps))


class TestBuildDeliverDescription(unittest.TestCase):
    """Leave what the robot ALREADY carries: the drop half of a transport, nothing before it."""

    def test_it_goes_to_the_staging_and_puts_the_load_down_and_picks_nothing(self):
        description = build_deliver_description(CATALOG, "entrega_b")
        self.assertEqual("deliver_box", description["category"])
        self.assertEqual(
            [
                {"category": "go_to_place", "description": "entrega_b_staging"},
                action("drop_box", "entrega_b"),
            ],
            activities(description),
        )
        kinds = [
            s["description"]["category"]
            for s in activities(description)
            if s["category"] == "perform_action"
        ]
        self.assertNotIn("pick_box", kinds)

    def test_it_is_the_second_half_of_a_transport_step_by_step(self):
        transport = activities(build_description(CATALOG, "recogida_a", "entrega_b", "box", 1))
        self.assertEqual(transport[2:], activities(build_deliver_description(CATALOG, "entrega_b")))

    def test_a_cart_keeps_the_orientation_of_the_station(self):
        description = build_deliver_description(CATALOG, "entrega_b", "cart")
        self.assertEqual("deliver_cart", description["category"])
        first, second = activities(description)
        self.assertEqual(
            {"waypoint": "entrega_b_staging", "orientation": math.radians(270.0)},
            first["description"],
        )
        self.assertEqual("drop_cart", second["description"]["category"])

    def test_it_is_one_phase_so_it_is_one_task(self):
        self.assertEqual(1, len(build_deliver_description(CATALOG, "entrega_b")["phases"]))

    def test_only_a_dropoff_station_is_a_place_to_leave_a_load(self):
        cases = [
            ("nowhere", "unknown_destination"),
            ("recogida_a", "not_a_dropoff"),
            ("cargador_1", "not_a_dropoff"),
        ]
        for destination, code in cases:
            with self.subTest(destination=destination):
                with self.assertRaises(TransportError) as error:
                    build_deliver_description(CATALOG, destination)
                self.assertEqual(code, error.exception.code)

    def test_a_dropoff_without_staging_is_not_a_station(self):
        catalog = {"destinations": [{"id": "entrega_x", "kind": "dropoff", "cart": None}]}
        with self.assertRaises(TransportError) as error:
            build_deliver_description(catalog, "entrega_x")
        self.assertEqual("not_a_station", error.exception.code)

    def test_a_load_that_is_not_known_and_a_missing_catalog_say_so(self):
        with self.assertRaises(TransportError) as error:
            build_deliver_description(CATALOG, "entrega_b", "pallet")
        self.assertEqual("invalid_load", error.exception.code)
        with self.assertRaises(TransportError) as error:
            build_deliver_description(None, "entrega_b")
        self.assertEqual("catalog_unavailable", error.exception.code)
