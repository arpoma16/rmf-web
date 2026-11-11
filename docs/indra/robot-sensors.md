# Robot sensors: camera, lidar and Nav2 map over REST

The api-server reads three kinds of ROS topics of a `bcr_bot` and serves them, so the dashboard and the
MCP of the AGVs need no rosbridge and no second robot registry. Code: `api_server/sensors.py` (cache and
conversions, standard library only) and `api_server/routes/robot_sensors.py` (routes, mounted at `/robots`
with the same `user_dep` as every other route).

## Endpoints

| Endpoint | Answer | ROS topic |
|---|---|---|
| `GET /robots/{robot}/camera` | `image/jpeg`: the latest frame, as published | `/{robot}/stereo_camera/right/image_raw/compressed` |
| `GET /robots/{robot}/lidar` | JSON: `frame_id`, `stamp`, `angle_min/max/increment`, `range_min/max`, `ranges` | `/{robot}/scan` |
| `GET /robots/{robot}/map` | `image/png`, grayscale, up is +y | `/{robot}/map` |
| `GET /robots/{robot}/map/info` | JSON: `resolution`, `width`, `height`, `origin {x, y, yaw}` | `/{robot}/map` |

- `{robot}` must be a robot of some fleet state (the RMF registry). Anything else is `404`, and no topic is
  subscribed. The name must also match `[A-Za-z0-9_]+`.
- No message in time is `503` (3 s for camera and lidar, 5 s for the map). A camera frame older than 1 s is
  never returned: the call waits for a new one.
- In `ranges`, a return without an echo (infinite or NaN in ROS) is `null`, because JSON cannot carry it.
  In the simulation about a third of the 361 points were `null`. A client that reads `null` as `0` will see
  obstacles that are not there: map it to infinity.
- The map is read **per robot**: every `map_server` is its own node, so the maps are never assumed equal.
  PNG gray levels: free 254, unknown 205, occupied 0. Pixel `(col, row)` is the cell
  `(col, height - 1 - row)`; cell `(0, 0)` is at `origin`.

## How it works

`SensorCache` subscribes to a topic on its first request and keeps the latest message. A subscription nobody
asked for in 30 s is dropped by a ROS timer (it runs on the spin thread, like the callbacks). The ROS node
spins in its own thread, so callbacks and the asyncio handlers meet only through a lock and
`call_soon_threadsafe`. The cache is a `singleton_dep` entered in `app.py` after the ROS node, so it follows
the node's lifecycle and closes its subscriptions on shutdown.

QoS (checked against the simulation, 2026-11-11): camera and lidar are published `RELIABLE`, and a
best-effort subscription (`qos_profile_sensor_data`) connects to both kinds of publisher. The map is
`RELIABLE` + `TRANSIENT_LOCAL`, so the subscription asks for the same to receive the latched map.

## Tests

`api_server/test_sensors.py` needs neither ROS nor the RMF message packages (the host has `rclpy` but not
`rmf_fleet_msgs`):

```bash
cd packages/api-server
TZ=UTC ../../.venv/bin/python -m unittest api_server.test_sensors
```

`api_server/routes/test_robot_sensors.py` starts the whole app, so it runs in the container. Keep it away
from a running simulation: its own ROS domain, its own port, the in-memory database of `test_config.py`:

```bash
docker exec indra_dev_container bash -lc 'source /tmp/ros_env.sh; cd /ariac_ws/src/rmf-web/packages/api-server &&
  ROS_DOMAIN_ID=87 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST RMF_API_SERVER_TEST_PORT=18123 \
  RMF_API_SERVER_CONFIG=$PWD/scripts/test_config.py TZ=UTC \
  /ariac_ws/src/rmf-web/.venv/bin/python -m unittest api_server.routes.test_robot_sensors -v'
```

Those two use a fake cache. The real subscription path was checked against the live robots with a throwaway
node that used `SensorCache` and the router's own constants: a 35 KB JPEG, 361 lidar points and a 1171x1486
map as a 21 KB PNG, for `bcr_bot_1` and `bcr_bot_3`.

## Not covered

- The running api-server only has these routes after a restart; nothing here reloads it.
- The topic names are those of the `bcr_bot` (constants at the top of `robot_sensors.py`). Another robot
  model needs them configurable.
- Pylint and Pyright (`pnpm run lint`) were not run; `black` and `isort` were.
