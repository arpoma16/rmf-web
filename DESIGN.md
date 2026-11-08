# Sistema de diseño — Flota LINCE

Solo cambia el estilo del panel de monitoreo (colores, bordes, tipografía). Estructura y lógica no se tocan. El chat lateral es un iframe del GCS: conserva sus propios colores.

## Dónde vive

- Tokens (valores de los tres temas): `packages/rmf-dashboard-framework/examples/demo/design-tokens.ts`.
- Tema MUI construido a partir de los tokens: `packages/rmf-dashboard-framework/examples/demo/theme.ts`. Los colores se cambian ahí, no en los componentes.
- Chips de estado: `src/components/status-chip.tsx`.

## Cambiar de tema

Por defecto es **A**. Para usar otro: `VITE_DESIGN_THEME=B` (o `C`) en el entorno de Vite (por ejemplo `.env.local` en `examples/demo/`) y reiniciar Vite. También se puede cambiar `DEFAULT_DESIGN_THEME` en `design-tokens.ts`.

## Tokens

| Token | A · Verde petróleo | B · Azul corporativo | C · Grafito oscuro |
|---|---|---|---|
| bg (fondo de página) | `#EDF1F2` | `#EEF2F8` | `#0F1418` |
| surface (tarjetas) | `#FFFFFF` | `#FFFFFF` | `#171E24` |
| head (cabecera de tarjeta) | `#F4F8F8` | `#F4F7FC` | `#1C252C` |
| border | `#DAE3E5` | `#D8E0EE` | `#2A353E` |
| text | `#1B2B30` | `#17233A` | `#E6EDF2` |
| muted | `#566B71` | `#55647F` | `#93A4B1` |
| title (título de tarjeta) | `#0B5A62` | `#1E3A8A` | `#FFD08A` |
| appbar | `#11252B` | `#0F2747` | `#0A0E11` |
| appbarText | `#EAF3F4` | `#EAF0FA` | `#E6EDF2` |
| tabMuted | `#9DB6BA` | `#A9BCD9` | `#8FA1AE` |
| tabLine (pestaña activa) | `#3CC9C0` | `#5AA9FF` | `#F5A524` |
| accent (botón primario) | `#0E7C86` | `#1D4ED8` | `#F5A524` |
| accentText | `#FFFFFF` | `#FFFFFF` | `#1A1200` |
| accentInk | `#0B6169` | `#1D4ED8` | `#F5B84A` |
| accentLine | `#7FB5BA` | `#93ADEB` | `#6B5321` |
| warm (badge) / warmText | `#FFB020` / `#1F1500` | `#FFB020` / `#1F1500` | `#F5A524` / `#1A1200` |
| idleBg / idleFg | `#FFF0D6` / `#8A4B00` | `#FFF0D6` / `#8A4B00` | `#3A2E12` / `#FFC969` |
| okBg / okFg | `#DDF3E4` / `#14663A` | `#DDF3E4` / `#14663A` | `#12331F` / `#6FDB9B` |
| clBg / clFg (closed) | `#FDE4E1` / `#A02A22` | `#FDE4E1` / `#A02A22` | `#3B1B1A` / `#FF9A92` |
| mapBg | `#E4ECEE` | `#E3E9F3` | `#11171B` |

## Cómo se aplican en el tema MUI

| Token | Clave del tema |
|---|---|
| bg / surface | `palette.background.default` / `.paper` |
| border | `palette.divider` |
| text / muted | `palette.text.primary` / `.secondary` |
| accent / accentText / accentLine | `palette.primary.main` / `.contrastText` / `.light` (y `secondary.main`, usado por NEW TASK) |
| accentInk | `palette.info.main` (iconos de los controles del mapa) |
| okFg·okBg, clFg·clBg, idleFg·idleBg | `palette.success`, `.error`, `.warning` → `main` (texto) y `light` (fondo) del chip |
| mapBg | `palette.mapBackground` (campo propio, declarado en `src/components/theme.ts`) |
| appbar, appbarText, tabMuted, tabLine | variante `sticky` de `MuiAppBar` |
| head, title | variante `static` de `MuiAppBar` (cabecera de cada tarjeta) |
| warm / warmText | `MuiBadge` `colorSecondary` (campana) |

## Estados (chips)

Píldora con punto y texto en mayúsculas; el estado siempre se ve en el texto, no solo por el color.

| Estado | Chip |
|---|---|
| Robot `WORKING`, puerta `ONLINE`, puerta `OPEN` | ok |
| Robot `ERROR`, puerta `OFFLINE`, puerta `CLOSED` | closed (rojo) |
| Robot `IDLE`, `CHARGING` y otros; puerta `MOVING` | idle (ámbar) |
| Robot `OFFLINE`, `UNINITIALIZED`, `DECOMMISSIONED`; puerta desconocida | neutro (muted sobre bg) |

## Tipografía

`Inter, system-ui, sans-serif`. La fuente Inter no está empaquetada: si el equipo no la tiene instalada se usa `system-ui`. Números de tablas con `font-variant-numeric: tabular-nums`.
