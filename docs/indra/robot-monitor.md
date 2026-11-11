# Monitor de robots (micro-app del dashboard)

Ventana del dashboard con la lista de robots y, al elegir uno, lo que ve su cámara. Inspirado en la lista
de dispositivos del GCS; se copió el comportamiento, no el código (usa RxJS, MUI y los hooks del dashboard).
Decisiones 16 a 19 de `indra_agv_mcp/docs/DECISIONES.md`. La API que consume: `docs/indra/robot-sensors.md`.

## Qué hace

1. **Lista** (`role="listbox"`): robot, flota, estado (`StatusChip`), batería, plataforma (`SUBIDA` / `BAJADA` / `—`) y tarea.
2. **Cámara** del robot elegido, debajo de la lista, con un solo stream abierto a la vez.
3. **Resalte en el mapa**: anillo naranja y etiqueta con el nombre del robot elegido, hasta que se elige otro o se pulsa «dejar de ver».

Está en los workspaces `home` y `robots` del demo (`examples/demo/main.tsx`) y en el `appRegistry` del workspace `Custom`.

## Piezas

| Archivo (en `packages/rmf-dashboard-framework/src/`) | Rol |
|---|---|
| `micro-apps/robot-monitor-app.ts` | `createMicroApp('robot-monitor', 'Monitor de robots', …)`; exportado como `robotMonitorApp` |
| `components/robot-monitor/robot-monitor.tsx` | Contenedor: sondeo de datos, selección, panel de cámara |
| `components/robot-monitor/robot-monitor-row.tsx` | Fila de la lista (tono del chip, texto de la plataforma) |
| `components/robot-monitor/robot-camera-view.tsx` | `buildStreamUrl`, `cameraAvailability` y el `<img>` MJPEG con sus estados |
| `components/robot-monitor/use-polling.ts` | Sondeo con cancelación al desmontar y sin rondas solapadas |
| `services/robot-sensors.ts` | Cliente a mano de `/robots/platform` y `/robots/capabilities` (el cliente OpenAPI generado no las conoce y no se toca) |
| `components/map/robot-three-maker.tsx` | `SelectedRobotMark` (anillo + etiqueta); `map.tsx` le pasa `selected` |
| `config.ts` | `getWebVideoUrl()` |

## Datos y refrescos

| Dato | Origen | Cada |
|---|---|---|
| Robots, estado, batería, tarea | `GET /fleets` (cliente generado) y `GET /tasks?task_id=…` para el nombre de la tarea | 3 s |
| Plataforma `lift_up` | `GET /robots/platform` | 2 s |
| Capacidades (cámaras) | `GET /robots/capabilities` | 10 s (el descubrimiento DDS tarda unos segundos tras arrancar el api-server) |

Una ronda fallida de plataforma o capacidades conserva el último valor; una de flotas muestra un aviso.
La tarea es solo una etiqueta: si no se puede leer su estado se muestra el `task_id`.

El cliente de sensores necesita la URL del api-server. `RmfApi` ahora expone `apiServerUrl` (opcional en la interfaz,
así los mocks no cambian) y el token sale del mismo `Authenticator` que usa el cliente generado.

## Selección

Todo pasa por `AppEvents.robotSelect` (`[flota, robot] | null`): la lista lo emite al elegir, y escucha el de la tabla de
robots, de la ventana de tareas y del mapa. El mapa lo escucha para centrar el robot (ya existía) y ahora también para
resaltarlo. Si el mapa se monta después de elegir (cambio de pestaña) no recibe la selección anterior: `robotSelect` no
repite el último valor. Para que lo hiciera habría que volverlo un `BehaviorSubject`, que cambia a todos sus consumidores.

## Cámara

`web_video_server` (no el api-server): `http://<host>:8080/stream?topic=<topic>&width=480&height=360&quality=60`,
sin autenticación. `<host>` es `window.location.hostname`; se cambia con `VITE_WEB_VIDEO_URL` (p. ej. en `.env.local`
de `examples/demo/`, y reiniciar Vite). `0.0.0.0` es donde escucha el servidor, no una dirección para el navegador.

- Solo se pide el `topic` de `cameras` de `/robots/capabilities` (el primero). Un topic que no existe devuelve 200 y no envía datos.
- Los `/` del topic van sin codificar (`?topic=/bcr_bot_1/...`), que es la forma documentada y la probada.
- Al cambiar de robot o desmontar, `img.src = ''` cierra la conexión (el stream no termina solo).
- Estados: consultando capacidades · sin cámara · declarada pero sin publicar (`declared_but_missing` filtrado a cámaras:
  se descartan `lidar_2d`, `lift` y `map`) · cargando · en vivo · error. Sin ningún fotograma en 10 s pasa a error, con «Reintentar».

## Cómo probarlo

```bash
cd packages/rmf-dashboard-framework
npx vitest run --configLoader runner -c <config temporal>     # ver «Gotchas» de rmf-web/CLAUDE.md
```

Verlo funcionando: api-server en `:8000` con las rutas de sensores, `web_video_server` en `:8080` y la simulación con los
`bcr_bot`. El Vite del contenedor (`:5173`) no recoge archivos nuevos sin reiniciarlo.

## Verificado

- 2026-11-11, en un Chrome headless contra el api-server y la simulación reales: lista de los 3 `bcr_bot`, clic en uno,
  stream de 480x360 y anillo + etiqueta en el mapa. Un bug solo visible ahí (`data-testid` en un `<group>` de three-fiber
  rompía el Canvas) quedó corregido: en los objetos de three-fiber usar `name`, no atributos con guion.
- El usuario probó la cámara en el dashboard y funciona.
- Vitest: suite completa en verde (82 archivos, 233 tests); `tsc` y prettier limpios.

## Sin verificar

- Una cámara `compressed`: no se probó que `web_video_server` la sirva. El componente la pide igual y, si no llega, termina en error.
- La plataforma **subida** (`SUBIDA`) en vivo: en la simulación estaba todo abajo. Solo está cubierta por los tests.
- La lista con un robot con tarea activa en vivo (no había tareas).
- El tamaño del anillo del mapa es fijo (1,0–1,3 m); con un icono de robot mucho más grande que el círculo por defecto puede quedar corto.
- El enlace entre un `robotSelect` emitido desde la tabla o el mapa y la lista está cubierto por test, no se hizo clic en ellos en el navegador.
