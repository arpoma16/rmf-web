"""
Camera, lidar and Nav2 map of a robot, read from its ROS topics.

The robot name must be one RMF knows (a robot of some fleet state): that is the single
registry, and it also keeps arbitrary text out of the topic name.
"""

import contextlib
import re
from typing import Annotated

import rclpy.qos
from fastapi import APIRouter, Depends, HTTPException, Response
from nav_msgs.msg import OccupancyGrid
from sensor_msgs.msg import CompressedImage, LaserScan

from api_server.fast_io.singleton_dep import singleton_dep
from api_server.repositories import FleetRepository
from api_server.ros import get_ros_node
from api_server.sensors import (
    SensorCache,
    SensorTimeout,
    laser_scan_to_dict,
    occupancy_info,
    occupancy_to_png,
)

router = APIRouter(tags=["Robot sensors"])


@singleton_dep
@contextlib.contextmanager
def get_sensor_cache():
    """
    Entered at app startup after the ROS node (see `app.py`): the node is recreated every
    time the app starts, so the cache has to follow its lifecycle.
    """
    cache = SensorCache(get_ros_node())
    try:
        yield cache
    finally:
        cache.close()


# Topic of each sensor, by robot name (the Nav2 / Gazebo namespace of the bcr_bot).
CAMERA_TOPIC = "/{robot}/stereo_camera/right/image_raw/compressed"
LIDAR_TOPIC = "/{robot}/scan"
MAP_TOPIC = "/{robot}/map"

# Best effort connects to both reliable and best-effort publishers.
_SENSOR_QOS = rclpy.qos.qos_profile_sensor_data
# The Nav2 map_server latches its map: ask for it the same way to receive the last one.
_MAP_QOS = rclpy.qos.QoSProfile(
    history=rclpy.qos.HistoryPolicy.KEEP_LAST,
    depth=1,
    reliability=rclpy.qos.ReliabilityPolicy.RELIABLE,
    durability=rclpy.qos.DurabilityPolicy.TRANSIENT_LOCAL,
)

_ROBOT_NAME = re.compile(r"^[A-Za-z0-9_]+$")
_NO_STORE = {"Cache-Control": "no-store"}


async def known_robot(
    robot: str, repo: Annotated[FleetRepository, Depends(FleetRepository)]
) -> str:
    if _ROBOT_NAME.match(robot):
        for fleet in await repo.get_all_fleets():
            if robot in (fleet.robots or {}):
                return robot
    raise HTTPException(status_code=404, detail=f"Unknown robot: {robot}")


async def _latest(
    cache: SensorCache,
    topic: str,
    msg_type,
    qos,
    *,
    timeout: float,
    max_age: float | None,
):
    try:
        return await cache.get(topic, msg_type, qos, timeout=timeout, max_age=max_age)
    except SensorTimeout:
        raise HTTPException(
            status_code=503, detail=f"No message on {topic} within {timeout:g} s"
        ) from None


def _image_media_type(image_format: str) -> str | None:
    lowered = image_format.lower()
    if "jpeg" in lowered or "jpg" in lowered:
        return "image/jpeg"
    if "png" in lowered:
        return "image/png"
    return None


@router.get(
    "/{robot}/camera",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}, "image/png": {}}}},
)
async def get_camera(
    robot: Annotated[str, Depends(known_robot)],
    cache: Annotated[SensorCache, Depends(get_sensor_cache)],
):
    """The latest frame of the robot's front camera, as the image it was published in."""
    topic = CAMERA_TOPIC.format(robot=robot)
    msg = await _latest(
        cache, topic, CompressedImage, _SENSOR_QOS, timeout=3.0, max_age=1.0
    )
    media_type = _image_media_type(msg.format)
    if media_type is None:
        raise HTTPException(
            status_code=415, detail=f"Unsupported image format: {msg.format!r}"
        )
    return Response(content=bytes(msg.data), media_type=media_type, headers=_NO_STORE)


@router.get("/{robot}/lidar")
async def get_lidar(
    robot: Annotated[str, Depends(known_robot)],
    cache: Annotated[SensorCache, Depends(get_sensor_cache)],
):
    """
    The latest 2D laser scan. A return without an echo (infinite or NaN in ROS) is
    `null` in `ranges`, because JSON cannot carry it.
    """
    topic = LIDAR_TOPIC.format(robot=robot)
    msg = await _latest(cache, topic, LaserScan, _SENSOR_QOS, timeout=3.0, max_age=1.0)
    return laser_scan_to_dict(msg)


@router.get("/{robot}/map/info")
async def get_map_info(
    robot: Annotated[str, Depends(known_robot)],
    cache: Annotated[SensorCache, Depends(get_sensor_cache)],
):
    """Resolution, size and origin of the Nav2 map that this robot localizes against."""
    topic = MAP_TOPIC.format(robot=robot)
    msg = await _latest(
        cache, topic, OccupancyGrid, _MAP_QOS, timeout=5.0, max_age=None
    )
    return occupancy_info(msg)


@router.get(
    "/{robot}/map",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
async def get_map(
    robot: Annotated[str, Depends(known_robot)],
    cache: Annotated[SensorCache, Depends(get_sensor_cache)],
):
    """
    The Nav2 map of this robot as a PNG (up is +y). Each robot has its own map server,
    so the maps are read per robot and never assumed to be the same.
    """
    topic = MAP_TOPIC.format(robot=robot)
    msg = await _latest(
        cache, topic, OccupancyGrid, _MAP_QOS, timeout=5.0, max_age=None
    )
    return Response(content=occupancy_to_png(msg), media_type="image/png")
