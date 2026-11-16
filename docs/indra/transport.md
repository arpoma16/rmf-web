# Transporte de carga: `POST /indra/transport`, el formulario del dashboard y la tool del MCP

Llevar una caja (o un carro) de una estación de recogida a una de entrega, **una o varias veces**, diciendo solo **de dónde y a dónde**.
Quien pide no arma el procedimiento: lo arma el api-server a partir del catálogo de destinos de `indra`.

## La tarea

Una sola tarea RMF `compose` con una fase `sequence`. Cada ciclo son cuatro pasos y se repite `repeat` veces (siempre suelta antes de volver a recoger):

```
go_to_place <recogida>_staging  ->  perform_action pick_box
go_to_place <entrega>_staging   ->  perform_action drop_box
```

- RMF lleva al robot a cada **staging** (así planifica el tráfico y respeta los grupos mutex de las estaciones).
- El resto de la estación lo hace el fleet adapter con la acción: entra recto al centro, sube o baja la plataforma y sale en reversa
  (`indra_fleet_adapter/README.md`, «Boxes, no cart»).
- `load: box` (por defecto): `pick_box` / `drop_box`, con el nombre del staging en el `go_to_place` y **sin orientación** (la acción gira al eje de la estación).
- `load: cart`: `pick_cart` / `drop_cart`, con la orientación de cada estación en cada `go_to_place` (la pide el contrato de carros).
- Al terminar la tarea, la flota manda al robot a su cargador (`finishing_request: park`), para que no se quede estorbando en un staging.
- **Una tarea con `repeat` ciclos** (no `repeat` tareas): un solo `task_id`, un solo robot, y cancelar la tarea las detiene todas.

La construcción es una función pura: `packages/api-server/api_server/indra_transport.py` (`build_description`).

## El endpoint

`POST /indra/transport` (autenticado como el resto del api-server).

```json
{"from": "recogida_propulsion_2", "to": "entrega_propulsion_2", "load": "box", "repeat": 3, "robot": "bcr_bot_1"}
```

| Campo | Por defecto | Qué es |
|---|---|---|
| `from` | — | id de una recogida del catálogo (`recogida_*`) |
| `to` | — | id de una entrega del catálogo (`entrega_*`) |
| `load` | `box` | `box` o `cart` |
| `repeat` | `1` | 1 a 50 ciclos en la misma tarea |
| `robot` | — | sin él, RMF elige robot (`/tasks/dispatch_task`); con él, `/tasks/robot_task` |
| `fleet` | `bcr_bot` | flota del robot |

La respuesta es la de RMF (`state.booking.id` es el `task_id`). Se despacha con las mismas funciones que `/tasks/dispatch_task` y `/tasks/robot_task`,
así que la tarea queda guardada igual (`requester` = el usuario, etiquetas `transport`, `load=box`, `repeat=N`, `from=<id>`, `to=<id>`, `pickup=<id>` y `destination=<id>`; las dos últimas son las que lee el panel de tareas del dashboard en sus columnas
**Pickup** y **Destination**, las mismas que escribe el formulario Transport; `from`/`to` son las que lee el MCP). Las etiquetas viajan con el estado de cualquier tarea
(`GET /tasks`), con o sin robot: una tarea con `robot` explícito no deja la petición guardada (solo `/tasks/dispatch_task` lo hace), así que de ahí no se puede leer a dónde iba.

Rechazos antes de llegar a RMF: `400 {"detail": {"error": <código>, "detail": <motivo>}}` con `unknown_destination`, `not_a_pickup`, `not_a_dropoff`,
`not_a_station` (sin staging), `invalid_load`, `invalid_repeat`; `503 catalog_unavailable` si el api-server no tiene el catálogo; `422` si falta `from` o `to`.
Si RMF rechaza la tarea, sigue siendo `400` con `errors` (lo mismo que `/tasks/dispatch_task`).

**Un robot que ya lleva carga no puede recoger otra:** con `robot` y la plataforma arriba (`lift_up`, todavía no hay sensor de carga) responde `409 robot_carrying` al instante, en vez de mandarlo de
viaje y que el adapter cancele la tarea en la estación («the platform is already up»). Sin `robot` no se comprueba (RMF elige y aquí no se sabe cuál). Solo una carga CONOCIDA bloquea: si el
estado de la plataforma no se sabe (`null`), la tarea sigue. La validación de la petición (400) va antes.

## Entregar lo que el robot ya lleva: `POST /indra/deliver`

Para soltar la carga que quedó en la plataforma (p. ej. tras cancelar una entrega con `force`). Es la segunda mitad de un transporte (ir al staging de la entrega y soltar) y **no recoge nada**; no
hay una tarea de «solo recoger» a propósito: con `finishing_request: park` el robot terminaría yéndose al cargador con la carga.

```json
{"to": "entrega_almacen_materiales", "robot": "bcr_bot_1", "load": "box"}
```

| Campo | Por defecto | Qué es |
|---|---|---|
| `to` | — | id de una entrega del catálogo (`entrega_*`) |
| `robot` | — | **obligatorio**: la carga está en ESE robot (`/tasks/robot_task`); vacío → `422` |
| `load` | `box` | `box` o `cart` |
| `fleet` | `bcr_bot` | flota del robot |

Una tarea `compose` de categoría `deliver_box` (o `deliver_cart`) con 2 pasos, etiquetas `deliver`, `load=box`, `to=<id>` y `destination=<id>` (sin `pickup`: no recoge nada; su columna Pickup sale `n/a`). Rechazos: los mismos `400` de la entrega (`unknown_destination`,
`not_a_dropoff`, `not_a_station`, `invalid_load`), `503 catalog_unavailable`, y **`409 robot_not_carrying`** si se SABE que el robot no lleva nada (el adapter fallaría el `drop_box` recién tras el viaje:
«the platform is not up»); si no se sabe, sigue.

**El catálogo.** Viene de `indra/config/destinations.json` (derivado de `material_points.yaml` con `indra/scripts/export_destinations.py`) y llega como el campo
`indra_destinations` de la config del api-server (`indra/config/rmf_api_server_config.py`, igual que `fleet_sensors`). `INDRA_DESTINATIONS_FILE` usa otro archivo
(si se pide así, debe existir). Hay que **reiniciar el api-server** para que lea un catálogo nuevo.

## El panel de tareas del dashboard

- **Orden.** Por defecto ordena por la columna **Date** (`unix_millis_request_time`, hora real) y no por `Start Time`. RMF corre en sim-time, que se reinicia con cada arranque, y ordenando por `Start Time` descendente las
  tareas de la corrida actual quedaban debajo de las de las corridas anteriores, en las últimas páginas (el 2026-11-16 las del día caían en las páginas 5 a 7 de 10 por página). Pickup y Destination salen de las etiquetas `pickup=` y `destination=`.
- **Sin arreglar:** la exportación a CSV filtra por rango de `start_time` (`getPastMonthTasks`), así que con sim-time diría «No tasks found over the past month».

## El formulario del dashboard

En «Create task» aparece el tipo **Transport** (si la app lo permite: `{ taskDefinitionId: 'transport' }` en `tasks.allowedTasks`; ya está en `examples/demo/main.tsx`,
que es el dashboard que levanta `factory_rmf.launch.py`). Campos: **Pickup**, **Dropoff**, **Times** (1 a 50) y la carga (por ahora solo **Box**, fija).

- Las estaciones salen de los waypoints del mapa: un `recogida_*` / `entrega_*` solo se ofrece si existe también su `<id>_staging`. Con el mapa de la fábrica son 16 recogidas y 17 entregas.
- Entra por el flujo normal de tareas del dashboard (`dispatchTask`): se puede **elegir robot** y **programarla** (recurrente), y la tarea sale con la etiqueta de reserva `transport`.
- Código: `packages/rmf-dashboard-framework/src/components/tasks/types/transport.tsx` (+ registro en `task-form.tsx` y `types/utils.ts`).
- **La tarea del formulario está duplicada** a propósito con la del api-server (el formulario usa el flujo del dashboard, que ya sabe programar y elegir robot). Se comprobó el 2026-11-15
  que producen exactamente el mismo JSON (caja, 3 repeticiones, catálogo real). Si se cambia la plantilla, hay que cambiar las dos y volver a comparar.
- Los carros no están en el formulario (necesitan la orientación de cada estación, que el mapa no trae en los nombres); se piden por el endpoint o el MCP.

## La tool del MCP

`agv_transport {from, to, load?, repeat?, robot?}` en `indra_agv_mcp`: valida los nombres contra el catálogo (los mismos códigos que `agv_transport_cart`) y hace **una** llamada a
`POST /indra/transport`. Los rechazos del api-server vuelven como `{ok: false, error, detail}`. Contrato: `lince_manager/contracts/rmf_task_api.md` §2.6.
Para que el chat la use hay que agregarla a `allowedTools` del agente en el repo del GCS (`agv.md`); eso no está hecho.

## Verificado y no verificado

Tests: `api_server.test_indra_transport` y `api_server.routes.test_indra` (api-server; la suite completa, 177, pasa; incluye `/indra/deliver`, `robot_carrying` y una clase que usa la plataforma real, sin parchearla), `transport.test.tsx` (dashboard) y `test/rmfTasks.test.ts` (MCP, 66).

En simulación, el 2026-11-15, con los tres a la vez sobre estaciones distintas:
- **Endpoint** (token real): sin token `401`; destino inexistente, entrega como recogida, carga inválida, `repeat` 0 y 51 → `400` con su código; falta `to` → `422`.
  Con `box`, `repeat: 2` y sin robot, RMF eligió `bcr_bot_1` y la tarea (una sola, etiquetas `transport`, `load=box`, `repeat=2`) quedó `completed` en 379 s, con 2 subidas y 2 bajadas (0,05–0,10 m del centro).
- **Tool del MCP** contra el api-server real: `agv_transport` creó la tarea y RMF la terminó (`completed`, 231 s); sus rechazos locales (`not_a_cart_station`, `unknown_robot`) salieron bien.
- **Formulario del dashboard:** una tarea mandada desde él en el navegador (`requester: admin`, etiquetas `task_definition_id=transport` y `destination=entrega_propulsion_1`) fue a `bcr_bot_3`,
  que levantó la caja en `recogida_almacen_materiales2` (0,19 m) y la soltó en `entrega_propulsion_1` (0,09 m). Al escribir esto la tarea seguía `underway` (reversa y vuelta al cargador).
- La tarea del formulario (TypeScript) y la del api-server (Python) dan el mismo JSON para el mismo pedido (caja, 3 repeticiones, catálogo real).

No verificado: `load: cart` en simulación por este camino; el formulario con programación (recurrente) y con elegir robot; que los tres sigan bien con más de 3 robots o con dos tareas pidiendo la misma
estación a la vez por estos caminos (el `mutex` lo cubre, probado con dos robots, pero no por el endpoint). El comportamiento del robot en la estación: `indra_fleet_adapter/README.md` («Boxes, no cart»).
