"""
Camera, lidar, Nav2 map and platform state of a robot, read from its ROS topics, and what
each robot offers.

The robot name must be one RMF knows (a robot of some fleet state): that is the single
registry, and it also keeps arbitrary text out of the topic name. The topics come from the
configuration of the robot's fleet (`AppConfig.fleet_sensors`, the `sensors` block of the
fleet config), relative to the namespace of the robot. What a robot offers is what its
fleet declares AND what it publishes right now: a declared sensor with no publisher is
reported as missing, so a configuration that drifts from the launch shows up.
"""

import asyncio
import contextlib
import re
from dataclasses import dataclass
from typing import Annotated

import rclpy.qos
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from nav_msgs.msg import OccupancyGrid
from sensor_msgs.msg import CompressedImage, Image, LaserScan
from std_msgs.msg import Bool

from api_server.app_config import app_config
from api_server.fast_io.singleton_dep import singleton_dep
from api_server.repositories import FleetRepository
from api_server.ros import get_ros_node
from api_server.sensors import (
    CameraSpec,
    FleetSensors,
    SensorCache,
    SensorTimeout,
    UnsupportedImageEncoding,
    image_to_png,
    laser_scan_to_dict,
    occupancy_info,
    occupancy_to_png,
    sensors_of,
    topic_of,
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


_CAMERA_MESSAGES = {"raw": Image, "compressed": CompressedImage}

# Best effort connects to both reliable and best-effort publishers.
_SENSOR_QOS = rclpy.qos.qos_profile_sensor_data
# The Nav2 map_server latches its map and the lift controller its state: ask for it the same
# way to receive the last value as soon as we subscribe.
_LATCHED_QOS = rclpy.qos.QoSProfile(
    history=rclpy.qos.HistoryPolicy.KEEP_LAST,
    depth=1,
    reliability=rclpy.qos.ReliabilityPolicy.RELIABLE,
    durability=rclpy.qos.DurabilityPolicy.TRANSIENT_LOCAL,
)

_ROBOT_NAME = re.compile(r"^[A-Za-z0-9_]+$")
_NO_STORE = {"Cache-Control": "no-store"}


@dataclass(frozen=True)
class KnownRobot:
    name: str
    fleet: str
    sensors: FleetSensors


async def _known_robots(repo: FleetRepository) -> list[KnownRobot]:
    robots = {}
    for fleet in await repo.get_all_fleets():
        fleet_name = fleet.name or ""
        sensors = sensors_of(app_config.fleet_sensors, fleet_name)
        for name in fleet.robots or {}:
            if _ROBOT_NAME.match(name):
                robots[name] = KnownRobot(name, fleet_name, sensors)
    return sorted(robots.values(), key=lambda robot: robot.name)


async def known_robot(
    robot: str, repo: Annotated[FleetRepository, Depends(FleetRepository)]
) -> KnownRobot:
    if _ROBOT_NAME.match(robot):
        for known in await _known_robots(repo):
            if known.name == robot:
                return known
    raise HTTPException(status_code=404, detail=f"Unknown robot: {robot}")


def _declared(relative: str | None, what: str, robot: KnownRobot) -> str:
    """The topic of a sensor the fleet declares; 404 when it does not declare it."""
    if relative is None:
        raise HTTPException(
            status_code=404, detail=f"{robot.name} does not declare a {what}"
        )
    return topic_of(robot.name, relative)


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


def _publishing(cache: SensorCache, robot: KnownRobot, relative: str | None) -> bool:
    return relative is not None and cache.has_publisher(topic_of(robot.name, relative))


def _available_cameras(cache: SensorCache, robot: KnownRobot) -> list[CameraSpec]:
    return [
        camera
        for camera in robot.sensors.cameras
        if _publishing(cache, robot, camera.topic)
    ]


def _image_media_type(image_format: str) -> str | None:
    lowered = image_format.lower()
    if "jpeg" in lowered or "jpg" in lowered:
        return "image/jpeg"
    if "png" in lowered:
        return "image/png"
    return None


def _capabilities(cache: SensorCache, robot: KnownRobot) -> dict:
    sensors = robot.sensors
    cameras = _available_cameras(cache, robot)
    publishing = {
        "lidar_2d": _publishing(cache, robot, sensors.lidar_2d),
        "lift": _publishing(cache, robot, sensors.lift_state),
        "map": _publishing(cache, robot, sensors.map),
    }
    declared = {
        "lidar_2d": sensors.lidar_2d,
        "lift": sensors.lift_state,
        "map": sensors.map,
    }
    missing = [camera.name for camera in sensors.cameras if camera not in cameras]
    missing += [
        name
        for name, relative in declared.items()
        if relative is not None and not publishing[name]
    ]
    return {
        "fleet": robot.fleet,
        "cameras": [
            {
                "name": camera.name,
                "topic": topic_of(robot.name, camera.topic),
                "kind": camera.kind,
            }
            for camera in cameras
        ],
        **publishing,
        "declared_but_missing": missing,
    }


@router.get("/capabilities")
async def get_capabilities(
    repo: Annotated[FleetRepository, Depends(FleetRepository)],
    cache: Annotated[SensorCache, Depends(get_sensor_cache)],
):
    """
    What each robot offers: what the configuration of its fleet declares AND the robot
    publishes right now. `cameras` carries the topic of each one (what a video server needs);
    `declared_but_missing` names what is declared but has no publisher (not launched, or the
    ROS graph is still being discovered). Asking subscribes to nothing.
    """
    return {
        "robots": {
            robot.name: _capabilities(cache, robot)
            for robot in await _known_robots(repo)
        }
    }


@router.get("/platform")
async def get_platform(
    repo: Annotated[FleetRepository, Depends(FleetRepository)],
    cache: Annotated[SensorCache, Depends(get_sensor_cache)],
):
    """
    The state of the lift platform of every robot, like its battery: `lift_up` is true while
    the platform is raised (the robot carries a cart) and `null` when the fleet declares no
    lift, the robot does not publish it or it has not reported yet.
    """

    async def one(robot: KnownRobot):
        return robot.name, {"lift_up": await _lift_up(cache, robot)}

    robots = await _known_robots(repo)
    return {"robots": dict(await asyncio.gather(*(one(robot) for robot in robots)))}


async def _lift_up(cache: SensorCache, robot: KnownRobot) -> bool | None:
    """True while the platform is raised, None when the fleet declares no lift, the robot does not
    publish it or it has not reported yet."""
    if not _publishing(cache, robot, robot.sensors.lift_state):
        return None
    topic = topic_of(robot.name, robot.sensors.lift_state)
    try:
        msg = await cache.get(topic, Bool, _LATCHED_QOS, timeout=1.0, max_age=None)
    except SensorTimeout:
        return None
    return bool(msg.data)


async def lift_up_of(repo: FleetRepository, cache: SensorCache, robot_name: str) -> bool | None:
    """`lift_up` of ONE robot, for the routes that must know whether it carries a load. None when
    it is not known (the robot is not in the fleet, no lift, no report): callers never block on that."""
    for robot in await _known_robots(repo):
        if robot.name == robot_name:
            return await _lift_up(cache, robot)
    return None


@router.get(
    "/{robot}/camera",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}, "image/png": {}}}},
)
async def get_camera(
    robot: Annotated[KnownRobot, Depends(known_robot)],
    cache: Annotated[SensorCache, Depends(get_sensor_cache)],
    source: Annotated[
        str | None,
        Query(
            description="Camera name from /robots/capabilities; the first one if omitted"
        ),
    ] = None,
):
    """
    The latest frame of a camera of the robot. A compressed camera is returned as it was
    published (JPEG or PNG); a raw one is encoded as a PNG.
    """
    cameras = _available_cameras(cache, robot)
    if source is not None:
        cameras = [camera for camera in cameras if camera.name == source]
    if not cameras:
        detail = f"{robot.name} has no camera" + (f" named {source}" if source else "")
        raise HTTPException(status_code=404, detail=detail)
    camera = cameras[0]
    msg = await _latest(
        cache,
        topic_of(robot.name, camera.topic),
        _CAMERA_MESSAGES[camera.kind],
        _SENSOR_QOS,
        timeout=3.0,
        max_age=1.0,
    )
    if camera.kind == "raw":
        try:
            content = image_to_png(msg)
        except UnsupportedImageEncoding:
            raise HTTPException(
                status_code=415, detail=f"Unsupported image encoding: {msg.encoding!r}"
            ) from None
        except ValueError as error:
            raise HTTPException(status_code=502, detail=str(error)) from None
        return Response(content=content, media_type="image/png", headers=_NO_STORE)
    media_type = _image_media_type(msg.format)
    if media_type is None:
        raise HTTPException(
            status_code=415, detail=f"Unsupported image format: {msg.format!r}"
        )
    return Response(content=bytes(msg.data), media_type=media_type, headers=_NO_STORE)


@router.get("/{robot}/lidar")
async def get_lidar(
    robot: Annotated[KnownRobot, Depends(known_robot)],
    cache: Annotated[SensorCache, Depends(get_sensor_cache)],
):
    """
    The latest 2D laser scan. A return without an echo (infinite or NaN in ROS) is
    `null` in `ranges`, because JSON cannot carry it.
    """
    topic = _declared(robot.sensors.lidar_2d, "2D lidar", robot)
    msg = await _latest(cache, topic, LaserScan, _SENSOR_QOS, timeout=3.0, max_age=1.0)
    return laser_scan_to_dict(msg)


@router.get("/{robot}/map/info")
async def get_map_info(
    robot: Annotated[KnownRobot, Depends(known_robot)],
    cache: Annotated[SensorCache, Depends(get_sensor_cache)],
):
    """Resolution, size and origin of the Nav2 map that this robot localizes against."""
    topic = _declared(robot.sensors.map, "map", robot)
    msg = await _latest(
        cache, topic, OccupancyGrid, _LATCHED_QOS, timeout=5.0, max_age=None
    )
    return occupancy_info(msg)


@router.get(
    "/{robot}/map",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
async def get_map(
    robot: Annotated[KnownRobot, Depends(known_robot)],
    cache: Annotated[SensorCache, Depends(get_sensor_cache)],
):
    """
    The Nav2 map of this robot as a PNG (up is +y). Each robot has its own map server,
    so the maps are read per robot and never assumed to be the same.
    """
    topic = _declared(robot.sensors.map, "map", robot)
    msg = await _latest(
        cache, topic, OccupancyGrid, _LATCHED_QOS, timeout=5.0, max_age=None
    )
    return Response(content=occupancy_to_png(msg), media_type="image/png")
