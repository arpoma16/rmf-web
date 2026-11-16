"""Endpoints of the Indra factory.

`POST /indra/transport` takes a load at a pickup station and leaves it at a dropoff station,
optionally several times: the caller says WHERE (two destination ids from the catalog), not how.
The api-server turns it into one RMF compose task (see api_server.indra_transport) and dispatches it
exactly as `POST /tasks/dispatch_task` (RMF picks the robot) or `POST /tasks/robot_task` (`robot`
given) does. The dashboard form and the MCP tool both call this, so the task template lives once.
"""
import time
from typing import Annotated, Optional

from fastapi import Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api_server import models as mdl
from api_server.app_config import app_config
from api_server.authenticator import user_dep
from api_server.fast_io import FastIORouter
from api_server.indra_transport import (
    MAX_REPEAT,
    TransportError,
    build_deliver_description,
    build_description,
)
from api_server.logging import LoggerAdapter, get_logger
from api_server.models import User
from api_server.repositories import FleetRepository, TaskRepository
from api_server.rmf_io import RmfService, get_tasks_service
from api_server.routes.robot_sensors import SensorCache, get_sensor_cache, lift_up_of
from api_server.routes.tasks.tasks import post_dispatch_task, post_robot_task

router = FastIORouter(tags=["Indra"])


async def _lift_up(robot: str, repo: FleetRepository, cache: SensorCache) -> Optional[bool]:
    """Does the robot carry a load? True while its lift platform is up (there is no load sensor yet),
    None when that is not known: an unknown never blocks a request, only a known state does."""
    return await lift_up_of(repo, cache, robot)


def _catalog() -> Optional[dict]:
    """indra's destinations.json (the `indra_destinations` field of the config), or None."""
    return app_config.indra_destinations


class TransportRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(
        alias="from", description="Id of the pickup station (a `recogida_*` of the catalog)"
    )
    to: str = Field(description="Id of the dropoff station (an `entrega_*` of the catalog)")
    # `load` and `repeat` are validated by build_description, so a wrong value gets a code and a
    # reason (400) and not a bare schema error.
    load: str = Field(
        default="box", description="What is carried: `box` (on the lift platform) or `cart`"
    )
    repeat: int = Field(
        default=1,
        description=f"How many times to repeat pick and drop, in ONE task (1 to {MAX_REPEAT})",
    )
    robot: Optional[str] = Field(
        default=None, description="Robot to do it. Without it RMF picks one"
    )
    fleet: str = Field(default="bcr_bot", description="Fleet of the robot")


@router.post(
    "/transport",
    response_model=None,
    responses={
        400: {"description": "The request cannot become a task, or RMF refused it"},
        409: {"description": "`robot_carrying`: the named robot already carries a load"},
        503: {"description": "The destinations catalog is not loaded"},
    },
)
async def post_transport(
    request: Annotated[TransportRequest, Body(...)],
    user: Annotated[User, Depends(user_dep)],
    task_repo: Annotated[TaskRepository, Depends(TaskRepository)],
    logger: Annotated[LoggerAdapter, Depends(get_logger)],
    tasks_service: Annotated[RmfService, Depends(get_tasks_service)],
    fleet_repo: Annotated[FleetRepository, Depends(FleetRepository)],
    sensor_cache: Annotated[SensorCache, Depends(get_sensor_cache)],
):
    try:
        description = build_description(
            _catalog(), request.from_, request.to, request.load, request.repeat
        )
    except TransportError as error:
        status = 503 if error.code == "catalog_unavailable" else 400
        raise HTTPException(status, detail={"error": error.code, "detail": str(error)}) from error

    # A task starts with a pick, and a robot that carries a load cannot pick another one: say so now
    # and do not send it on a trip that the fleet adapter would cancel at the station. Only with a
    # named robot (without one RMF chooses and nothing here knows which); only a KNOWN load blocks.
    if request.robot and await _lift_up(request.robot, fleet_repo, sensor_cache) is True:
        raise HTTPException(
            409,
            detail={
                "error": "robot_carrying",
                "detail": f"[{request.robot}] carries a load (its lift platform is up), so it cannot "
                "pick another one: deliver what it carries first (POST /indra/deliver)",
            },
        )

    def task_request(**extra) -> mdl.TaskRequest:
        return mdl.TaskRequest(
            category="compose",
            description=description,
            requester=user.username,
            unix_millis_request_time=int(time.time() * 1000),
            # The labels travel with the task state (GET /tasks), so whoever lists tasks (the MCP, the
            # dashboard) can say where a delivery goes, with or without a robot (a robot task saves no request).
            # `pickup=` and `destination=` are the ones the dashboard table reads for its Pickup and
            # Destination columns (the Transport form writes them); `from=` and `to=` are what the MCP reads.
            labels=[
                "transport",
                f"load={request.load}",
                f"repeat={request.repeat}",
                f"from={request.from_}",
                f"to={request.to}",
                f"pickup={request.from_}",
                f"destination={request.to}",
            ],
            **extra,
        )

    logger.debug("transport %s -> %s x%s (%s)", request.from_, request.to, request.repeat, request.load)
    if request.robot:
        return await post_robot_task(
            mdl.RobotTaskRequest(
                type="robot_task_request",
                robot=request.robot,
                fleet=request.fleet,
                request=task_request(),
            ),
            task_repo,
            tasks_service,
        )
    return await post_dispatch_task(
        mdl.DispatchTaskRequest(
            type="dispatch_task_request", request=task_request(fleet_name=request.fleet)
        ),
        task_repo,
        logger,
        tasks_service,
    )


class DeliverRequest(BaseModel):
    to: str = Field(description="Id of the dropoff station (an `entrega_*` of the catalog)")
    robot: str = Field(
        min_length=1,
        description="Robot that carries the load. Required: the load is on THAT robot, so RMF does not choose",
    )
    load: str = Field(
        default="box", description="What the robot carries: `box` (on the lift platform) or `cart`"
    )
    fleet: str = Field(default="bcr_bot", description="Fleet of the robot")


@router.post(
    "/deliver",
    response_model=None,
    responses={
        400: {"description": "The request cannot become a task, or RMF refused it"},
        409: {"description": "`robot_not_carrying`: the robot is known to carry nothing"},
        503: {"description": "The destinations catalog is not loaded"},
    },
)
async def post_deliver(
    request: Annotated[DeliverRequest, Body(...)],
    user: Annotated[User, Depends(user_dep)],
    task_repo: Annotated[TaskRepository, Depends(TaskRepository)],
    logger: Annotated[LoggerAdapter, Depends(get_logger)],
    tasks_service: Annotated[RmfService, Depends(get_tasks_service)],
    fleet_repo: Annotated[FleetRepository, Depends(FleetRepository)],
    sensor_cache: Annotated[SensorCache, Depends(get_sensor_cache)],
):
    """Leave at a dropoff station the load that a robot ALREADY carries: the way to put down what a
    cancelled delivery left on its platform. One task for that robot (go to the staging of the station
    and put the load down); nothing is picked up."""
    try:
        description = build_deliver_description(_catalog(), request.to, request.load)
    except TransportError as error:
        status = 503 if error.code == "catalog_unavailable" else 400
        raise HTTPException(status, detail={"error": error.code, "detail": str(error)}) from error

    # The fleet adapter would fail the drop ("the platform is not up") only after the whole trip.
    if await _lift_up(request.robot, fleet_repo, sensor_cache) is False:
        raise HTTPException(
            409,
            detail={
                "error": "robot_not_carrying",
                "detail": f"[{request.robot}] carries nothing (its lift platform is down): "
                "there is nothing to deliver",
            },
        )

    logger.debug("deliver %s -> %s (%s)", request.robot, request.to, request.load)
    return await post_robot_task(
        mdl.RobotTaskRequest(
            type="robot_task_request",
            robot=request.robot,
            fleet=request.fleet,
            request=mdl.TaskRequest(
                category="compose",
                description=description,
                requester=user.username,
                unix_millis_request_time=int(time.time() * 1000),
                labels=[
                    "deliver",
                    f"load={request.load}",
                    f"to={request.to}",
                    f"destination={request.to}",
                ],
            ),
        ),
        task_repo,
        tasks_service,
    )
