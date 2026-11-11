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

    def close(self) -> None:
        """Drops every subscription and the purge timer. Called when the app shuts down."""
        with self._lock:
            dropped = list(self._entries.values())
            self._entries.clear()
        for entry in dropped:
            self._node.destroy_subscription(entry.subscription)
        self._node.destroy_timer(self._timer)


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


def encode_png_gray(
    width: int, height: int, pixels: bytes, flip_vertical: bool = False
) -> bytes:
    """8-bit grayscale PNG from `width * height` bytes, row-major from the first row."""
    if len(pixels) != width * height:
        raise ValueError(f"expected {width * height} pixels, got {len(pixels)}")
    rows = range(height - 1, -1, -1) if flip_vertical else range(height)
    raw = b"".join(b"\x00" + pixels[y * width : (y + 1) * width] for y in rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, 6))
        + _png_chunk(b"IEND", b"")
    )


def occupancy_to_png(msg: Any) -> bytes:
    """
    PNG of a `nav_msgs/OccupancyGrid`, oriented like a map image (up is +y).
    Pure standard library: no Pillow or numpy needed.
    """
    width, height = int(msg.info.width), int(msg.info.height)
    data = msg.data
    raw = data.tobytes() if hasattr(data, "tobytes") else bytes(array.array("b", data))
    return encode_png_gray(width, height, raw.translate(_GRAY), flip_vertical=True)
