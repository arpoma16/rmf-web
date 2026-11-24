# Stack del api-server y del dashboard de `rmf-web` (revisión de código, 2026-11-04)

> Movido el 2026-11-08 desde `indra/docs/RMF.md` §13 (texto original: `git -C /home/grvc/work/Indra/indra show c64b1f6:docs/RMF.md`). Es lectura de código de la versión 0.3.0 de entonces; el fork ya se actualizó con upstream `jazzy` (2026-11-05), así que los detalles de versiones pueden haber cambiado. Se conserva la numeración 13.x.

Fuente: `rmf-web/packages/{api-server,rmf-dashboard-framework,api-client,rmf-models}` (clon de terceros, versión 0.3.0, con 1 parche local en `gateway.py`).
Motivo de la revisión: valorar si el chat LLM puede vivir en el servidor/cliente de RMF en vez de en el GCS aparte (`indra/CLAUDE.md › LLM`).
Todo lo de esta sección sale de leer el código; el arranque y las respuestas de los endpoints ya verificados están en el registro de simulación (`lince_manager/fase3/implementacion.md` §2.1).

### 13.1 Cliente web: `rmf-dashboard-framework` (el que sirve vite en :5173)
| Capa | Tecnología |
|---|---|
| UI | React 18, MUI 5 (`@mui/material`, `@mui/x-data-grid` v5, `@mui/x-date-pickers`), Emotion |
| Mapa | three.js 0.166 con `@react-three/fiber` 8 y `@react-three/drei` (render 3D de puertas, ascensores y robots; no usa Leaflet) |
| Layout | `react-grid-layout`: ventanas arrastrables ("micro-apps") dentro de pestañas (`Workspace`, `LocallyPersistentWorkspace`) |
| Datos | rxjs 7: `DefaultRmfApi` (`services/rmf-api.ts`) expone `Observable`s (`fleetsObs`, `doorsObs`, `liftsObs`, `getTaskStateObs`, alertas...) |
| Cliente de API | paquete `api-client`: generado con openapi-generator desde el OpenAPI del servidor; axios 1.8 + `socket.io-client` 4.7 (`SioClient`) |
| Auth | `StubAuthenticator` en el demo; `keycloak-js` 25 como alternativa (ejemplo en `examples/keycloak`) |
| Router | react-router 6 |
| Tooling | Vite 5 + plugin React SWC, TypeScript 5.5, Vitest 3 + testing-library, Storybook 8, ESLint 9, pnpm |

- Entrada: `<RmfDashboard apiServerUrl trajectoryServerUrl authenticator tasks tabs resources ...>`; el demo es `examples/demo/main.tsx`
  (pestañas Map, Robots, Tasks, Custom). Config de vite del demo: `examples/shared/vite.config.ts` (host `0.0.0.0`, puerto 5173).
- Micro-apps de serie (`src/micro-apps`): map, doors, lifts, robots, robot-mutex-groups, tasks.
  Se crean con `createMicroApp(appId, nombre, () => import('./foo'), () => props)` (carga dinámica para code-splitting; `docs/micro-apps.md`).
  Las micro-apps pueden guardar ajustes con `useSettings` / `useAppController`.
- `trajectoryServerUrl` = `http://localhost:8006` (trayectorias de robots). No comprobé qué proceso lo sirve en nuestro stack
  (probablemente `schedule_visualizer_node` de `rmf_visualization`).
- **Límite relevante para `bcr_bot`:** `AllowedTask.taskDefinitionId` es una unión cerrada de 4 valores
  (`patrol`, `delivery`, `compose-clean`, `custom_compose`) y el `RmfDashboard` lanza error con cualquier otro. Una tarea propia (p. ej. `pick_cart`) exige tocar el framework.

### 13.2 Servidor: `api-server` (:8000)
| Capa | Tecnología |
|---|---|
| Web | FastAPI 0.109 + uvicorn + python-socketio, envueltos en un `FastIO` propio (`fast_io/`): añade rutas `@router.sub(...)` que emiten `Observable`s de reactivex por socket.io |
| Modelos | pydantic 2; modelos de RMF generados (`models/rmf_api`, `models/ros_pydantic`) |
| BD | tortoise-orm sobre SQLite (`sqlite:///rmf_api.db`); Postgres/MySQL soportados. Tablas en `models/tortoise_models` (tareas, estados de flota, logs, alertas, usuarios, permisos, tareas programadas...) |
| Auth | JWT (pyjwt); claim `preferred_username`; en dev, secret fijo (`jwt_secret`). `builtin_admin` se crea al arrancar. Roles y permisos por grupo (`permissions.py`, rutas `/admin`) |
| ROS | un nodo `rclpy` (`rmf_api_server`) en un hilo aparte (`ros.py`) |
| Otros | `schedule` (tareas programadas), cache de ficheros del mapa en `/tmp/rmf_api_cache` servido en `/cache` |
| Config | módulo Python con variable `config`, apuntado por `RMF_API_SERVER_CONFIG` (el nuestro: `indra/config/rmf_api_server_config.py`) |

Estructura: `app.py` (arranque y routers), `routes/` (un router por recurso), `repositories/` (acceso a BD), `rmf_io/` (eventos reactivos y servicio de tareas),
`gateway.py` (suscripciones ROS), `routes/internal.py` (WebSocket del dispatcher).

### 13.3 Cómo se comunica con RMF
- **Enviar tareas y comandos:** `POST /tasks/dispatch_task` (y `robot_task`, `cancel_task`, `interrupt_task`, `kill_task`, `resume_task`, `rewind_task`, `skip_phase`, `task_discovery`, `activity_discovery`)
  publican un `rmf_task_msgs/ApiRequest` en `task_api_requests` y esperan la respuesta en `task_api_responses` (pseudo-servicio sobre pub/sub, `rmf_io/rmf_service.py`, QoS reliable + transient local).
- **Recibir estados:** el `rmf_dispatcher_node` (C++) abre WebSocket a `ws://localhost:8000/_internal` (`server_uri`) y envía `task_state_update`, `task_log_update`,
  `fleet_state_update`, `fleet_log_update`. El servidor los guarda y los reemite por socket.io. Al completar o fallar una tarea crea una alerta automática.
- **Puertas, ascensores, dispensadores, mapa, alarma de incendio:** `gateway.py` se suscribe a los topics ROS y publica `adapter_door_requests`, `adapter_lift_requests`,
  `delivery_alert_response`, `mutex_group_manual_release`, `fire_alarm_trigger` (de aquí viene el aviso de QoS incompatible visto en el arranque de la fase 0).
- **Superficie REST (documentada en `/docs`):** `tasks`, `scheduled_tasks`, `favorite_tasks`, `fleets` (estado, log, `decommission`, `unlock_mutex_group`), `doors`, `lifts`,
  `building_map`, `alerts`, `dispensers`, `ingestors`, `beacons`, `rios`, `admin`, `user`, `permissions`, `time`.
- **Parche local** (`git diff` del clon): en `gateway.py`, las llamadas `self._loop.create_task(...)` desde callbacks de ROS pasan a
  `self._loop.call_soon_threadsafe(self._loop.create_task, ...)` (los callbacks corren en otro hilo que el bucle asyncio).

### 13.4 Qué implica para meter el chat LLM aquí (valoración, no decisión) — **superada por D14**: micro-app con iframe del `/chat` del GCS (`lince_manager/decisions/decisiones.md`)
| Pieza | Opción A: dentro de RMF (api-server + dashboard) | Opción B: en el GCS (Node, ya existe) |
|---|---|---|
| UI del chat | micro-app React/MUI nueva + pestaña en `RmfDashboard` (camino previsto por el framework) | la del GCS |
| Llamada al LLM | router nuevo en el api-server (Python; las claves del LLM quedan en el servidor) o servicio aparte | ya hecha (SDKs anthropic/openai en `server/`, no revisados) |
| Herramientas del LLM | los endpoints REST de arriba, con auth y permisos ya resueltos | rosbridge (:9090) con topics/acciones sueltas, o REST de RMF |
| Coste | UI nueva, backend nuevo y mantener un clon de terceros | alinear nombres de robot y exponer lo necesario |

Puntos a tener en cuenta:
1. El LLM no debe llamarse desde el navegador (clave API): hace falta un backend en cualquier caso.
2. `rmf-web` es un clon con remote ajeno y un parche local sin respaldo: antes de añadirle código propio, fork o mover lo nuestro a un paquete propio (ya pendiente en §1 y en `RMF_ADAPTER_DESIGN.md`).
3. Endpoints nuevos en el api-server obligan a regenerar `api-client` (`generate-openapi`) o a llamar con axios a mano.
4. Las tareas propias del `bcr_bot` (`pick_cart`/`drop_cart`) tocan tanto el servidor (definición/validación) como el dashboard (unión cerrada de §13.1).
5. **No investigado:** cómo está hecho el chat del GCS (herramientas, prompts, estado de la conversación), qué endpoints concretos necesitaría el LLM, y si el dispatcher acepta tareas `perform_action` personalizadas por la API tal como las necesitamos. Es lo que habría que mirar antes de decidir A o B.
