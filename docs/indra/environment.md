# rmf-web en el devcontainer de Indra: receta de entorno

> Movido el 2026-11-08 desde `indra/docs/RMF.md` §11 (texto original: `git -C /home/grvc/work/Indra/indra show c64b1f6:docs/RMF.md`). Se descartó lo anterior al merge de upstream `jazzy` del 2026-11-05 (instalación con `pip` en el Python del sistema y su Dockerfile), que quedó obsoleto.
> El api-server corre con `rmf-web/.venv/bin/python` y lo lanza `indra/launch/factory_rmf.launch.py`. Notas de entorno de la herramienta (husky, `.vite-temp`): ver `../../CLAUDE.md`.

- **Python:** el código nuevo exige lo que fija `rmf-web/Pipfile.lock` (`tortoise-orm` 1.1.8, `fastapi` 0.141, `starlette` 1.6, `pydantic` 2.13...),
  aunque `setup.py` diga `>=`. Con el Python del sistema (`tortoise-orm` 0.21.7) muere al arrancar (`Tortoise.init() got an unexpected keyword argument '_enable_global_fallback'`).
  Solución: venv de pipenv en `rmf-web/.venv` (`--site-packages`, ve `rclpy` y los mensajes de ROS) y `factory_rmf.launch.py` lanza el api-server con
  `rmf-web/.venv/bin/python`. Reinstalar exactamente el lock: `cd rmf-web && .venv/bin/pipenv sync -d` (**no** `pipenv install`: relockea y reescribe `Pipfile.lock`).
  El venv vive en la carpeta montada: sobrevive a recrear el contenedor. El `RUN pip3 install` del Dockerfile se quitó (nunca se commiteó ni se reconstruyó la imagen);
  los paquetes que se instalaron a mano en el contenedor actual el 2026-11-04 siguen ahí hasta recrearlo, sin uso.
- **Node:** el contenedor tiene pnpm 12 (store `v11`; el Dockerfile instala pnpm sin fijar versión). Instalar y compilar:
  `cd rmf-web && CI=true pnpm install --frozen-lockfile --filter "rmf-dashboard-framework..."` y `pnpm --filter rmf-models --filter api-client run build`.
  Ojo: ese install también ejecuta el paquete `pipenv-install` (`pipenv install`), que reescribe `Pipfile.lock`: revertirlo con `git checkout -- Pipfile.lock` y correr `pipenv sync -d`.
- **Verificado en ejecución** (aislado, headless, Gazebo despausado): api-server arriba con la BD existente (`/rmf_api.db`, 8 puertas cargadas), 0 tracebacks,
  `/user` 200, `/building_map` (`factory`, L1, 8 puertas), `/fleets` con `tinyRobot1`, dashboard :5173 200, y el estado de las puertas se actualiza en vivo
  en la API y en la BD (`door_time` avanza): camino del fix de `gateway.py`.
