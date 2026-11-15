"""The transport task of the Indra factory: take a load at a pickup station and leave it at a dropoff
station, optionally several times, as ONE RMF compose task.

Pure (no FastAPI, no RMF): it only turns the destinations catalog (indra's destinations.json) and a
request into the `description` of a compose task. RMF drives the robot to each station's staging
(so it plans the traffic) and the fleet adapter does the rest of the station with an action:

    go_to_place <pickup>_staging -> perform_action pick_* -> go_to_place <dropoff>_staging
    -> perform_action drop_*      (repeated `repeat` times, always dropping before picking again)

load "box": a box on the lift platform (pick_box / drop_box, the fleet adapter drives straight into
the station). load "cart": a lift cart (pick_cart / drop_cart), which also needs the orientation
of the station at each staging.
"""
import copy
import math
from typing import Any, Optional

# One compose task of 4 * MAX_REPEAT activities. A bigger plant run is several requests.
MAX_REPEAT = 50

ACTIONS = {"box": ("pick_box", "drop_box"), "cart": ("pick_cart", "drop_cart")}
ACTION_DURATION_ESTIMATE_MS = 60000


class TransportError(ValueError):
    """The request cannot become a task. `code` is stable (for clients), the message says why."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


def _find(catalog: dict, destination_id: str) -> Optional[dict]:
    for destination in catalog.get("destinations") or []:
        if destination.get("id") == destination_id:
            return destination
    return None


def _station(catalog: dict, destination_id: str, kind: str, not_code: str) -> dict:
    destination = _find(catalog, destination_id)
    if destination is None:
        raise TransportError(
            "unknown_destination", f"[{destination_id}] is not a destination of the catalog"
        )
    if destination.get("kind") != kind:
        raise TransportError(
            not_code,
            f"[{destination_id}] is a {destination.get('kind')}, not a {kind} station",
        )
    cart = destination.get("cart")
    if not cart or not cart.get("staging"):
        raise TransportError(
            "not_a_station", f"[{destination_id}] has no staging: it is not a station"
        )
    return destination


def _go_to_staging(station: dict, load: str) -> dict:
    cart = station["cart"]
    if load == "cart":
        description: Any = {
            "waypoint": cart["staging"],
            "orientation": math.radians(float(cart["yaw_deg"])),
        }
    else:
        # A box needs no orientation: pick_box / drop_box turn to the station axis themselves.
        description = cart["staging"]
    return {"category": "go_to_place", "description": description}


def _action(category: str, station_id: str) -> dict:
    return {
        "category": "perform_action",
        "description": {
            "category": category,
            "description": {"station": station_id},
            "unix_millis_action_duration_estimate": ACTION_DURATION_ESTIMATE_MS,
            "use_tool_sink": False,
        },
    }


def build_description(
    catalog: Optional[dict], pickup: str, dropoff: str, load: str, repeat: int
) -> dict:
    """The `description` of the compose task. Raises TransportError (with a code) if it cannot work."""
    if not catalog:
        raise TransportError("catalog_unavailable", "the destinations catalog is not loaded")
    if load not in ACTIONS:
        raise TransportError("invalid_load", f"load [{load}] is not one of {sorted(ACTIONS)}")
    if isinstance(repeat, bool) or not isinstance(repeat, int) or not 1 <= repeat <= MAX_REPEAT:
        raise TransportError("invalid_repeat", f"repeat must be a whole number from 1 to {MAX_REPEAT}")
    pick_station = _station(catalog, pickup, "pickup", "not_a_pickup")
    drop_station = _station(catalog, dropoff, "dropoff", "not_a_dropoff")
    pick_action, drop_action = ACTIONS[load]

    cycle = [
        _go_to_staging(pick_station, load),
        _action(pick_action, pickup),
        _go_to_staging(drop_station, load),
        _action(drop_action, dropoff),
    ]
    return {
        "category": f"transport_{load}",
        "phases": [
            {
                "activity": {
                    "category": "sequence",
                    # copies: the steps of the list must not share one object
                    "description": {
                        "activities": [copy.deepcopy(step) for _ in range(repeat) for step in cycle]
                    },
                }
            }
        ],
    }
