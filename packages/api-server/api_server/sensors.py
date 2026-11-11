"""
Latest-message cache for ROS sensor topics (camera, lidar, Nav2 map), plus the pure
conversions the REST routes need (laser scan to JSON, occupancy grid to PNG).

The ROS node of the api-server spins in its own thread (see `api_server/ros.py`), so
subscription callbacks run there while the REST handlers run on the asyncio loop.
Everything that crosses that boundary goes through a lock, and waiting handlers are
woken with `call_soon_threadsafe`.

Subscriptions are created on the first request and dropped when nobody asked for the
topic for a while, so an idle camera costs nothing. Only the standard library is imported
here: the caller passes the node, the message type and the QoS, so this module is tested
without ROS (and without the RMF message packages).
"""

import array
import asyncio
import math
import re
import struct
import threading
import time
import zlib
from dataclasses import dataclass, field
from typing import Any, Callable


class SensorTimeout(Exception):
    """No (fresh enough) message arrived on the topic in time."""


@dataclass
class _Entry:
    subscription: Any
    msg: Any = None
    received_at: float = 0.0
    last_used: float = 0.0
    waiters: list = field(default_factory=list)  # [(loop, future)]


def _set_result(future: "asyncio.Future", msg: Any) -> None:
    if not future.done():
        future.set_result(msg)


class SensorCache:
    def __init__(
        self,
        node: Any,
        idle_ttl: float = 30.0,
        purge_period: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        """
        :param idle_ttl: seconds without a request after which a topic is unsubscribed.
        :param purge_period: seconds between purges. The purge runs as a ROS timer, so it
            executes on the spin thread, the same one that runs the callbacks.
        """
        self._node = node
        self._idle_ttl = idle_ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, _Entry] = {}
        self._timer = node.create_timer(purge_period, self.purge_idle)

    async def get(
        self,
        topic: str,
        msg_type: Any,
        qos: Any,
        *,
        timeout: float = 3.0,
        max_age: float | None = 1.0,
    ) -> Any:
        """
        Latest message of `topic`, subscribing on the first call.

        :param max_age: a cached message older than this many seconds is not returned:
            the call waits for a new one. `None` accepts any age (a latched map).
        :raises SensorTimeout: nothing usable arrived within `timeout` seconds.
        """
        loop = asyncio.get_running_loop()
        now = self._clock()
        with self._lock:
            entry = self._entries.get(topic)
            if entry is None:
                entry = _Entry(subscription=None)
                entry.subscription = self._node.create_subscription(
                    msg_type, topic, lambda msg, t=topic: self._on_msg(t, msg), qos
                )
                self._entries[topic] = entry
            entry.last_used = now
            if entry.msg is not None and (
                max_age is None or now - entry.received_at <= max_age
            ):
                return entry.msg
            future = loop.create_future()
            entry.waiters.append((loop, future))
        try:
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            with self._lock:
                entry = self._entries.get(topic)
                if entry is not None:
                    entry.waiters = [w for w in entry.waiters if w[1] is not future]
            raise SensorTimeout(topic) from None

    def _on_msg(self, topic: str, msg: Any) -> None:
        # Runs on the ROS spin thread.
        with self._lock:
            entry = self._entries.get(topic)
            if entry is None:
                return
            entry.msg = msg
            entry.received_at = self._clock()
            waiters, entry.waiters = entry.waiters, []
        for loop, future in waiters:
            try:
                loop.call_soon_threadsafe(_set_result, future, msg)
            except RuntimeError:
                pass  # the loop is already closed

    def purge_idle(self) -> None:
        """Drops the subscriptions nobody asked for in `idle_ttl` seconds."""
        now = self._clock()
        with self._lock:
            idle = [
                topic
                for topic, entry in self._entries.items()
                if not entry.waiters and now - entry.last_used > self._idle_ttl
            ]
            dropped = [self._entries.pop(topic) for topic in idle]
        for entry in dropped:
            self._node.destroy_subscription(entry.subscription)

    def topics(self) -> list[str]:
        with self._lock:
            return sorted(self._entries)

    def has_publisher(self, topic: str) -> bool:
        """Whether something publishes `topic` right now (what a robot really offers)."""
        return self._node.count_publishers(topic) > 0

    def close(self) -> None:
        """Drops every subscription and the purge timer. Called when the app shuts down."""
        with self._lock:
            dropped = list(self._entries.values())
            self._entries.clear()
        for entry in dropped:
            self._node.destroy_subscription(entry.subscription)
        self._node.destroy_timer(self._timer)


# ---------------------------------------------------------------------------
# What a fleet publishes (declared in its configuration)
# ---------------------------------------------------------------------------

CAMERA_KINDS = ("raw", "compressed")  # sensor_msgs/Image, sensor_msgs/CompressedImage


@dataclass(frozen=True)
class CameraSpec:
    name: str
    topic: str  # relative to the namespace of the robot, which is its name
    kind: str


@dataclass(frozen=True)
class FleetSensors:
    """The topics every robot of a fleet publishes, relative to the namespace of the robot."""

    cameras: tuple[CameraSpec, ...] = ()
    lidar_2d: str | None = None
    lift_state: str | None = None
    map: str | None = None


# What a bcr_bot was assumed to have before it was declared anywhere. Used only when the
# api-server is given no sensor configuration at all (`AppConfig.fleet_sensors` is None).
LEGACY_SENSORS = FleetSensors(
    cameras=(
        CameraSpec("front", "front_camera/image_raw", "raw"),
        CameraSpec(
            "stereo_right", "stereo_camera/right/image_raw/compressed", "compressed"
        ),
        CameraSpec(
            "stereo_left", "stereo_camera/left/image_raw/compressed", "compressed"
        ),
    ),
    lidar_2d="scan",
    lift_state="lift_state",
    map="map",
)

_SENSOR_NAME = re.compile(r"^[A-Za-z0-9_]+$")
# Relative on purpose: no leading slash and no `..`, so a topic cannot leave the namespace of
# the robot it is asked for.
_RELATIVE_TOPIC = re.compile(r"^[A-Za-z0-9_]+(/[A-Za-z0-9_]+)*$")


def _topic(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _RELATIVE_TOPIC.match(value):
        raise ValueError(
            f"{where}: expected a topic relative to the robot namespace "
            f"(like 'scan' or 'front_camera/image_raw', no leading '/'), got {value!r}"
        )
    return value


def parse_fleet_sensors(raw: Any, where: str = "sensors") -> FleetSensors:
    """
    Validates the `sensors` block of a fleet configuration:

        sensors:
          cameras:
            - {name: front, topic: front_camera/image_raw, kind: raw}
          lidar_2d: scan
          lift_state: lift_state
          map: map

    Every key is optional: what is not declared is not offered. Raises ValueError with the
    place of the mistake, so a wrong configuration stops the api-server when it starts, not
    at the first request.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: expected a mapping, got {type(raw).__name__}")
    unknown = set(raw) - {"cameras", "lidar_2d", "lift_state", "map"}
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}")
    cameras = []
    for index, entry in enumerate(raw.get("cameras") or []):
        place = f"{where}.cameras[{index}]"
        if not isinstance(entry, dict) or set(entry) != {"name", "topic", "kind"}:
            raise ValueError(f"{place}: expected exactly name, topic and kind")
        if not isinstance(entry["name"], str) or not _SENSOR_NAME.match(entry["name"]):
            raise ValueError(f"{place}.name: expected letters, digits and '_'")
        if entry["kind"] not in CAMERA_KINDS:
            raise ValueError(f"{place}.kind: expected one of {CAMERA_KINDS}")
        cameras.append(
            CameraSpec(
                entry["name"], _topic(entry["topic"], f"{place}.topic"), entry["kind"]
            )
        )
    names = [camera.name for camera in cameras]
    if len(set(names)) != len(names):
        raise ValueError(f"{where}.cameras: duplicate names in {names}")
    singles = {}
    for key in ("lidar_2d", "lift_state", "map"):
        value = raw.get(key)
        singles[key] = None if value is None else _topic(value, f"{where}.{key}")
    return FleetSensors(cameras=tuple(cameras), **singles)


def parse_fleet_sensors_config(raw: Any) -> "dict[str, FleetSensors] | None":
    """`{fleet name: sensors block}` as the api-server configuration gives it; None stays None."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"fleet_sensors: expected a mapping, got {type(raw).__name__}")
    return {
        str(fleet): parse_fleet_sensors(block, f"fleet_sensors[{fleet}]")
        for fleet, block in raw.items()
    }


def sensors_of(
    fleet_sensors: "dict[str, FleetSensors] | None", fleet_name: str
) -> FleetSensors:
    """What `fleet_name` publishes: LEGACY_SENSORS when nothing is configured, else only what
    its configuration declares (a fleet without a block offers nothing)."""
    if fleet_sensors is None:
        return LEGACY_SENSORS
    return fleet_sensors.get(fleet_name, FleetSensors())


def topic_of(robot: str, relative: str) -> str:
    return f"/{robot}/{relative}"


# ---------------------------------------------------------------------------
# Pure conversions
# ---------------------------------------------------------------------------


def _finite_or_none(value: float) -> float | None:
    """JSON has no inf/nan: an invalid lidar return (no echo) becomes `null`."""
    value = float(value)
    return value if math.isfinite(value) else None


def laser_scan_to_dict(msg: Any) -> dict:
    return {
        "frame_id": msg.header.frame_id,
        "stamp": {
            "sec": int(msg.header.stamp.sec),
            "nanosec": int(msg.header.stamp.nanosec),
        },
        "angle_min": float(msg.angle_min),
        "angle_max": float(msg.angle_max),
        "angle_increment": float(msg.angle_increment),
        "time_increment": float(msg.time_increment),
        "scan_time": float(msg.scan_time),
        "range_min": float(msg.range_min),
        "range_max": float(msg.range_max),
        "ranges": [_finite_or_none(r) for r in msg.ranges],
    }


def occupancy_info(msg: Any) -> dict:
    info = msg.info
    q = info.origin.orientation
    yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
    return {
        "frame_id": msg.header.frame_id,
        "resolution": float(info.resolution),
        "width": int(info.width),
        "height": int(info.height),
        "origin": {
            "x": float(info.origin.position.x),
            "y": float(info.origin.position.y),
            "yaw": yaw,
        },
        "image": (
            "PNG, grayscale: free 254, unknown 205, occupied 0. Row 0 is the top (largest y): "
            "pixel (col, row) is the cell (col, height - 1 - row); cell (0, 0) is at the origin."
        ),
    }


def _gray_table() -> bytes:
    """Maps a raw int8 occupancy value (as an unsigned byte) to a gray level."""
    table = bytearray(256)
    for raw in range(256):
        value = raw - 256 if raw > 127 else raw
        if value < 0:
            table[raw] = 205  # unknown
        elif value >= 100:
            table[raw] = 0  # occupied
        else:
            table[raw] = 254 - round(value * 254 / 100)
    return bytes(table)


_GRAY = _gray_table()


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def encode_png(
    width: int,
    height: int,
    pixels: bytes,
    channels: int = 1,
    flip_vertical: bool = False,
    level: int = 6,
) -> bytes:
    """
    8-bit PNG (1 channel: grayscale, 3: RGB) from `width * height * channels` bytes,
    row-major from the first row.
    """
    if channels not in (1, 3):
        raise ValueError(f"unsupported channel count: {channels}")
    stride = width * channels
    if len(pixels) != stride * height:
        raise ValueError(f"expected {stride * height} bytes, got {len(pixels)}")
    rows = range(height - 1, -1, -1) if flip_vertical else range(height)
    raw = b"".join(b"\x00" + pixels[y * stride : (y + 1) * stride] for y in rows)
    color_type = 0 if channels == 1 else 2
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(
            b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
        )
        + _png_chunk(b"IDAT", zlib.compress(raw, level))
        + _png_chunk(b"IEND", b"")
    )


def encode_png_gray(
    width: int, height: int, pixels: bytes, flip_vertical: bool = False
) -> bytes:
    """8-bit grayscale PNG from `width * height` bytes, row-major from the first row."""
    return encode_png(width, height, pixels, 1, flip_vertical)


class UnsupportedImageEncoding(ValueError):
    """A raw image whose encoding cannot be turned into a PNG here."""


_IMAGE_CHANNELS = {"rgb8": 3, "bgr8": 3, "mono8": 1}


def image_to_png(msg: Any) -> bytes:
    """
    PNG of a raw `sensor_msgs/Image` (rgb8, bgr8 or mono8). The camera of the simulation
    publishes raw frames, and the standard library has no JPEG encoder: a PNG keeps this
    module free of Pillow and numpy.
    """
    channels = _IMAGE_CHANNELS.get(msg.encoding)
    if channels is None:
        raise UnsupportedImageEncoding(msg.encoding)
    width, height, step = int(msg.width), int(msg.height), int(msg.step)
    row_bytes = width * channels
    data = bytes(msg.data)
    if step < row_bytes or len(data) < step * height:
        raise ValueError("image data is shorter than its width, height and step say")
    rows = []
    for y in range(height):
        row = data[y * step : y * step + row_bytes]
        if msg.encoding == "bgr8":
            swapped = bytearray(row)
            swapped[0::3] = row[2::3]
            swapped[2::3] = row[0::3]
            row = bytes(swapped)
        rows.append(row)
    return encode_png(width, height, b"".join(rows), channels, level=3)


def occupancy_to_png(msg: Any) -> bytes:
    """
    PNG of a `nav_msgs/OccupancyGrid`, oriented like a map image (up is +y).
    Pure standard library: no Pillow or numpy needed.
    """
    width, height = int(msg.info.width), int(msg.info.height)
    data = msg.data
    raw = data.tobytes() if hasattr(data, "tobytes") else bytes(array.array("b", data))
    return encode_png_gray(width, height, raw.translate(_GRAY), flip_vertical=True)
