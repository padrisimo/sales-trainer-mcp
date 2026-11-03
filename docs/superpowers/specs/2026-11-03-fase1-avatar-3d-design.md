# Design — Fase 1: Avatar 3D procedural + panel `/debug/visemes`

- **Fecha:** 2026-11-03
- **Tema:** fase1-avatar-3d
- **Estado:** Aprobado por el usuario (diseño) — spec pendiente de confirmación

## Context

La Fase 0 dejó el esqueleto del proyecto funcionando: el servidor MCP (`src/sales_trainer/mcp_server.py`, SDK `mcp` 2.x, clase `MCPServer`, transporte stdio) arranca uvicorn en un thread daemon con la app FastAPI de `src/sales_trainer/web/app.py`, que hoy sirve una única ruta `GET /` con HTML placeholder que ecoa el token de sesión. La suite tiene 7 tests en verde (4 de MCP, 2 de web, 1 e2e marcado `e2e`) y `ruff` limpio.

No existe todavía ningún directorio de estáticos, ningún asset 3D y ninguna dependencia JS. `MEMORY.md` exige que la animación de la boca se derive de **fonemas reales con sus tiempos reales** y prohíbe explícitamente animar por amplitud de audio o de forma aleatoria; el conjunto interno de visemas es el de Oculus, 15 valores. También exige JS servido en local, **sin CDN en tiempo de ejecución**, para que la aplicación funcione offline, y avatares sin licencias dudosas.

La Fase 1 construye la pieza sobre la que se apoyará el TTS de la Fase 2: una malla con los 15 morph targets de visema y una página de depuración que permita comprobarlos de uno en uno. En esta fase no hay audio: solo la geometría, el mapeo y la vista de depuración.

## Goal

Servir una escena Three.js con una cabeza 3D procedural que expone los 15 morph targets de visema Oculus y respira, parpadea y mueve la cabeza en bucle idle, más una página `/debug/visemes` con un botón por viseme que aplica ese morph target y muestra cuál está activo.

## Acceptance Criteria

1. `GET /debug/visemes` responde `200` con `content-type: text/html`.
2. La página dibuja un avatar 3D visible en un `<canvas>` y expone en `window.avatarDebug` el viseme activo y la lista de los 15 nombres.
3. Hay exactamente 15 botones de viseme más un botón de reset; pulsar uno aplica su morph target y actualiza el viseme activo mostrado en pantalla.
4. Los nombres de los morph targets son exactamente `sil, PP, FF, TH, DD, kk, CH, SS, nn, RR, aa, E, I, O, U`.
5. En idle el avatar parpadea, respira y tiene micro-movimiento de cabeza sin intervención del usuario.
6. Ningún recurso se carga desde un CDN: Three.js se sirve desde `/static/js/vendor/`.
7. `uv run ruff check .` limpio y la suite existente sigue en verde.

## Non-Goals

- TTS, audio, fonemas y líneas temporales de visemas (Fase 2).
- La tabla Python de visemas en `src/sales_trainer/voice/visemes.py` y sus tests: sin fonemas que mapear sería código muerto.
- Los tres personajes y sus avatares diferenciados, las expresiones ligadas al termómetro y las animaciones de reacción.
- La UI definitiva de sesión (niveles, termómetro, subtítulos) y los informes.
- Cualquier animación de boca derivada de amplitud o aleatoria, prohibida por `MEMORY.md`.

## Proposed Architecture

**Vendoring de Three.js.** Se instala `three` con npm en una versión fijada (`0.187.0`, verificada en el registry) y se copian los dos ficheros que el build ESM necesita: `build/three.module.js` (que importa `./three.core.js`) y `build/three.core.js`, ambos a `src/sales_trainer/web/static/js/vendor/`. Se sirve desde el propio proceso FastAPI mediante `app.mount("/static", StaticFiles(directory=...), name="static")` (verificado: `fastapi.staticfiles.StaticFiles` es importable en fastapi `0.162.0`). Motivo: cumple la regla de «sin CDN en runtime», no añade dependencias de build al proyecto Python y mantiene el fichero versionado en git. Se descarta instalar Three.js como dependencia de desarrollo con bundler (Vite/esbuild): añadiría un toolchain de build entero para un único fichero ESM.

**Avatar procedural.** La cabeza se construye por código en `avatar.js` sin modelos externos: cráneo y mandíbula a partir de geometrías de Three.js deformadas, ojos y cejas como mallas independientes, y una malla de boca a la que se le asignan los 15 morph targets. Cada viseme define posiciones de vértices de la boca (apertura, redondeo, cierre, dientes, labio inferior) y el morph target se crea con `geometry.morphAttributes.position`. Motivo: cero licencias, cero descargas en runtime y control total de los nombres de morph target, que es justo lo que la Fase 2 necesita enganchar. Se descarta GLB/VRM CC0 con morph targets Oculus porque obliga a verificar licencias, a mapear nombres ajenos y añade peso al repositorio.

**Separación de módulos.** `scene.js` (renderer, cámara, luces, bucle de render y reloj), `avatar.js` (construcción de la malla y de los morph targets), `visemes.js` (la lista de los 15 nombres y la función que aplica pesos con suavizado) y `debug.js` (botones, estado activo y `<canvas>`). `index.html` monta la escena normal; `debug/visemes.html` monta la misma escena con el panel. Motivo: la Fase 2 necesitará `visemes.js` y `avatar.js` sin arrastrar el panel de depuración.

**Idle.** El bucle de render avanza un reloj y aplica tres animaciones procedurales independientes: parpadeo periódico (escala vertical de las mallas de ojo), respiración (desplazamiento vertical suave del grupo cabeza/hombros) y micro-rotación de cabeza con dos senos de períodos distintos. No toca los morph targets de visema, de modo que el panel de depuración no compite con el idle: el viseme activo se aplica por encima.

**Rutas.** `/debug/visemes` se sirve con `HTMLResponse` leyendo el fichero del paquete (mismo patrón que el placeholder actual de `/`, sin motor de plantillas). `GET /` pasa a servir `index.html`, sustituyendo el placeholder de la Fase 0, porque el avatar es la vista natural de la aplicación y mantener dos HTML muertos sería peor. El eco del token de sesión que verificaba la Fase 0 se conserva en `index.html`.

## Files To Change

**Nuevos:**
- `src/sales_trainer/web/static/js/vendor/three.module.js` — Three.js `0.187.0` copiado de npm (importa `./three.core.js`).
- `src/sales_trainer/web/static/js/vendor/three.core.js` — núcleo ESM del que depende el anterior.
- `src/sales_trainer/web/static/js/visemes.js` — los 15 nombres, pesos por defecto y `applyViseme(mesh, name)`.
- `src/sales_trainer/web/static/js/avatar.js` — cabeza procedural y creación de los 15 morph targets.
- `src/sales_trainer/web/static/js/scene.js` — renderer, cámara, luces, idle y bucle.
- `src/sales_trainer/web/static/js/debug.js` — panel de botones y estado del viseme activo.
- `src/sales_trainer/web/static/index.html` — escena a pantalla completa.
- `src/sales_trainer/web/static/debug/visemes.html` — escena + panel.
- `tests/unit/test_debug_visemes_route.py` — `/debug/visemes` responde 200 text/html y carga el panel de depuración.
- `tests/js/avatar_smoke.mjs` — smoke en node: la lista son los 15 visemes exactos y `createAvatar()` expone 15 morph targets con esos nombres.
- `tests/unit/test_avatar_js.py` — ejecuta el smoke de node como test de pytest, para que corra con el resto de la suite.
- `tests/e2e/test_debug_visemes_page.py` — Playwright: 15 botones, clic en cada uno, estado activo cambia, sin errores de consola.

**Modificados:**
- `src/sales_trainer/web/app.py` — montar `/static`, servir `index.html` en `/` y `debug/visemes.html` en `/debug/visemes`.
- `tests/unit/test_web_app.py` — el test actual exige que `/` contenga el texto «Sales Trainer»; se ajusta para exigir el token ecoado y la referencia al canvas, manteniendo el criterio de la Fase 0 (la página responde y refleja la sesión).
- `pyproject.toml` — grupos de dependencias: `playwright` en dev; `three` no entra en Python, se fija en `package.json`.
- `package.json` (nuevo, raíz) — dependencia `three` fijada a `0.187.0` y `playwright` fijado para el e2e.
- `docs/decisions.md` — decisión del avatar procedural y del vendoring de Three.js, con sus límites.
- `AGENTS.md` — estado al cerrar la fase.

Se versiona también `src/sales_trainer/web/static/LICENSES.md` con la licencia de Three.js (MIT) y el origen del fichero.

## Testing Strategy

- **Unitario (Python):** `TestClient` comprueba que `/debug/visemes` responde 200 con `text/html` y que el HTML carga `debug.js`; el test de `/` de la Fase 0 se mantiene tal cual, porque `index.html` conserva el título «Sales Trainer» y el eco del token.
- **Unitario (node, vía pytest):** `tests/js/avatar_smoke.mjs` importa `visemes.js` y `avatar.js` sin DOM, comprueba que la lista es exactamente los 15 visemes Oculus y que la malla de boca expone 15 morph targets con esos nombres. Motivo: los nombres son el contrato con la Fase 2 y deben romper la suite si alguien los toca; es además la única comprobación de geometría que no depende de WebGL.
- **e2e (Playwright, Chromium headless):** arranca uvicorn por CLI en un puerto de prueba, abre `/debug/visemes`, espera a que `window.avatarDebug.ready` sea cierto, cuenta los botones de viseme (15), pulsa cada uno y verifica que `window.avatarDebug.active` coincide con el nombre pulsado; recoge los errores de consola y falla si hay alguno. Motivo: es la única forma de comprobar que el canvas se dibuja y que el mapeo funciona de verdad.
- **Manual:** `/debug/visemes` con un humano mirando la boca, que es el criterio real de «cada viseme se ve correcto».
- **Comandos:** `uv run pytest` (unit), `uv run pytest -m e2e` (e2e), `uv run ruff check .`.

## Risks And Mitigations

1. **WebGL no disponible en Chromium headless.** Mitigación: lanzar Chromium con SwiftShader (`--use-angle=swiftshader`) y, si el contexto WebGL sigue sin crearse, el e2e se limita a DOM y estado JS y el límite se documenta en `docs/decisions.md`; la comprobación visual queda como paso manual del criterio de fase.
2. **Los nombres de morph target se desalinean con la Fase 2.** Mitigación: los 15 nombres viven en un único sitio (`visemes.js`) y el test unitario de la ruta verifica que los 15 aparecen en el HTML, de modo que cualquier renombrado rompe la suite.
3. **Un avatar procedural feo que no permita juzgar los visemes.** Mitigación: la malla de boca se mantiene simple y legible (labios, apertura, dientes) y el panel incluye el viseme activo escrito en pantalla, para que el criterio no dependa solo de la estética.
4. **Crecimiento del repositorio por versionar el build ESM de Three.js** (~2 MB entre `three.module.js` y `three.core.js`). Mitigación: se versionan solo esos dos ficheros, sin `node_modules` (ignorado en git), que es el precio de la regla de no CDN.

## Decision Summary

- Avatar procedural construido por código; no se usan modelos GLB/VRM externos.
- Un solo avatar en esta fase; la variación por personaje llega con las fichas de personaje.
- Three.js `0.187.0` empaquetado en `static/js/vendor/` (`three.module.js` + `three.core.js`), servido por FastAPI con `StaticFiles`; sin CDN en runtime.
- Los 15 nombres de viseme Oculus se definen una sola vez en `visemes.js`.
- `/` pasa a servir el avatar; `/debug/visemes` sirve la misma escena con el panel.
- Idle (parpadeo, respiración, micro-cabeza) separado del control de visemes.
- La tabla Python de visemas y todo el audio quedan para la Fase 2.
- Sin animación de boca por amplitud ni aleatoria, en ningún caso.

## Open Questions

- Ninguna bloqueante. La única decisión diferida es si la verificación visual de los 15 visemes requiere además capturas de referencia; se resolverá al ejecutar el criterio de fase con el navegador delante.
