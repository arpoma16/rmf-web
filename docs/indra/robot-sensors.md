# Robot sensors: camera, lidar and Nav2 map over REST

The api-server reads three kinds of ROS topics of a `bcr_bot` and serves them, so the dashboard and the
MCP of the AGVs need no rosbridge and no second robot registry. Code: `api_server/sensors.py` (cache and
conversions, standard library only) and `api_server/routes/robot_sensors.py` (routes, mounted at `/robots`
with the same `user_dep` as every other route).

## Endpoints

| Endpoint | Answer | ROS topic |
|---|---|---|
| `GET /robots/{robot}/camera[?source=name]` | The latest frame of a declared camera that is publishing: JPEG or PNG as published for a compressed camera, `image/png` for a raw one | `sensors.cameras[]` of the fleet |
| `GET /robots/capabilities` | JSON `{robots: {<name>: {fleet, cameras: [{name, topic, kind}], lidar_2d, lift, map, declared_but_missing}}}`: what the fleet declares AND the robot publishes now | the fleet's `sensors` block + ROS graph introspection (subscribes to nothing) |
| `GET /robots/platform` | JSON `{robots: {<name>: {lift_up}}}`: `true` while the lift platform is raised (the robot carries a cart), `false` lowered, `null` without a lift or before it reports | `/{robot}/lift_state` (latched `std_msgs/Bool`) |
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

## Which topics: the `sensors` block of the fleet config

No topic is written in this code. What the robots of a fleet publish is declared once, in the fleet config
(`indra_fleet_adapter/config/bcr_bot_config.yaml`, next to the other things all the robots of a fleet share):

```yaml
sensors:
  cameras:
    - {name: front, topic: front_camera/image_raw, kind: raw}   # kind: raw | compressed
  lidar_2d: scan
  lift_state: lift_state
  map: map
```

- Topics are **relative to the namespace of the robot** (its name): `scan` is `/bcr_bot_1/scan`. A leading `/` or a
  `..` is refused, so a topic cannot leave the namespace.
- Every key is optional and **what is not declared is not offered**: a fleet with no block (a TinyRobot) has no camera,
  no lidar and no map, and its `/lidar` or `/map` answer `404` ("does not declare").
- The adapter and the fleet manager ignore the block. The api-server reads it at startup through
  `indra/config/rmf_api_server_config.py` into `AppConfig.fleet_sensors` (`INDRA_FLEET_CONFIGS` points to other files).
  A mistake in the block **stops the server when it starts**, saying where it is. With no block anywhere (`None`), the
  bcr_bot defaults apply (`LEGACY_SENSORS`), so nothing breaks.
- It must match what the robot is launched with (`front_camera_enabled`, `stereo_camera_enabled`,
  `two_d_lidar_enabled`... in `bcr_bot_gz_spawn.launch.py`). The first simulation of 2026-11-11 had a stereo pair and the
  next one a front camera, so this is exactly what changes.

`/robots/capabilities` returns what is declared **and** published right now: `cameras` (with their topic, which is what
a video server needs) holds only the ones with a publisher, and `declared_but_missing` names the declared sensors
nobody publishes (not launched, or the ROS graph is still being discovered). `/camera` serves the first available one
(or the one named in `source`). A robot with none answers `404` ("has no camera"), not a timeout.

- The depth image of the kinect (`32FC1`) is not declared, so it is not offered: it is not a camera to look at.
- A raw image (`rgb8`, `bgr8`, `mono8`) becomes a PNG with `zlib` (the standard library has no JPEG encoder); about
  105 KB for 640x480 in the simulation. Another encoding is `415`.
- Capabilities depend on the ROS graph discovery. A node that has just been created needs some seconds to see every
  publisher, so right after the api-server starts a robot may show fewer capabilities for a few seconds. Checked: a
  fresh node showed `bcr_bot_3` without camera and lidar after 3 s and complete after 12 s.

## Live video for the dashboard

The dashboard consumer of these routes and of the video is the "Monitor de robots" micro-app: `docs/indra/robot-monitor.md`.

Not served here. `web_video_server` (`ros2 run web_video_server web_video_server`, started by the `video` pane of
`run_rmf.yml`, port 8080 published by the compose) streams a raw image topic as MJPEG:

```
http://<host>:8080/stream?topic=/bcr_bot_1/front_camera/image_raw[&width=320&height=240&quality=50]
http://<host>:8080/snapshot?topic=/bcr_bot_1/front_camera/image_raw        (one JPEG)
```

Checked: `multipart/x-mixed-replace` with `Access-Control-Allow-Origin: *`, about 4.5 frames/s and 25 KB per frame at
640x480. `0.0.0.0` is the address it listens on, not a URL for a browser: use the host the dashboard was opened from.
It has no authentication. Asking for a topic that does not exist answers `200` and never sends data, so ask only for
the topics of `cameras` in `/robots/capabilities`. Whether it can stream a *compressed* camera was not checked.

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
- The namespace of a robot is assumed to be its name (true for the bcr_bot). A fleet whose robots have another
  namespace would need it in the block.
- The block is read once, when the api-server starts: changing the fleet config needs a restart.
- Pylint and Pyright (`pnpm run lint`) were not run; `black` and `isort` were.
