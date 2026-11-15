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
from api_server.indra_transport import MAX_REPEAT, TransportError, build_description
from api_server.logging import LoggerAdapter, get_logger
from api_server.models import User
from api_server.repositories import TaskRepository
from api_server.rmf_io import RmfService, get_tasks_service
from api_server.routes.tasks.tasks import post_dispatch_task, post_robot_task

router = FastIORouter(tags=["Indra"])


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
        503: {"description": "The destinations catalog is not loaded"},
    },
)
async def post_transport(
    request: Annotated[TransportRequest, Body(...)],
    user: Annotated[User, Depends(user_dep)],
    task_repo: Annotated[TaskRepository, Depends(TaskRepository)],
    logger: Annotated[LoggerAdapter, Depends(get_logger)],
    tasks_service: Annotated[RmfService, Depends(get_tasks_service)],
):
    try:
        description = build_description(
            _catalog(), request.from_, request.to, request.load, request.repeat
        )
    except TransportError as error:
        status = 503 if error.code == "catalog_unavailable" else 400
        raise HTTPException(status, detail={"error": error.code, "detail": str(error)}) from error

    def task_request(**extra) -> mdl.TaskRequest:
        return mdl.TaskRequest(
            category="compose",
            description=description,
            requester=user.username,
            unix_millis_request_time=int(time.time() * 1000),
            labels=["transport", f"load={request.load}", f"repeat={request.repeat}"],
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
