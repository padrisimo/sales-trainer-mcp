# Decisiones del proyecto

## 2026-11-03 — Fase 0: arranque del servidor web (esqueleto)

- **Decisión:** el servidor web (FastAPI + uvicorn) arranca en un thread daemon dentro del proceso MCP (SDK `mcp`, clase `MCPServer`, transporte stdio).
- **Alternativa descartada:** proceso hijo del MCP.
- **Motivo:** menor complejidad de gestión en Fase 0; la memoria del proyecto contempla «arranca en un hilo o proceso hijo».
- **Consecuencias:** el thread daemon construye la app FastAPI desde `src/sales_trainer/web/app.py` y arranca uvicorn sobre ella; bind `127.0.0.1`, puerto por defecto `8765` configurable con `SALES_TRAINER_PORT`.
- **Desvío del plan:** `uv_build` deriva el módulo del nombre del proyecto (`sales_trainer_mcp`); se fija `[tool.uv.build-backend] module-name = "sales_trainer"` en `pyproject.toml` para mantener el layout `src/sales_trainer/` de la memoria.
- **Límite conocido:** `sales_trainer_start` no valida `Origin` todavía porque no hay WebSocket; llega en la fase de audio.

## 2026-11-03 — Fase 1: avatar procedural y Three.js vendorizado

- **Decisión:** el avatar de la Fase 1 se construye por código (primitivas de Three.js) con 15 morph targets de visema; no se usan modelos GLB/VRM.
- **Alternativa descartada:** empaquetar un modelo CC0 con morph targets Oculus o expresiones VRM.
- **Motivo:** cero riesgo de licencia, cero descargas en runtime, y los nombres de los morph targets son nuestros, que es el contrato que la Fase 2 necesita.
- **Three.js:** `0.187.0` versionado en `src/sales_trainer/web/static/js/vendor/` (`three.module.js` + `three.core.js`, el primero importa el segundo). Se sirve con `StaticFiles`; `node_modules/` está ignorado.
- **Boca curvo-esférica:** la malla de la boca recalcula su `z` con la superficie del cráneo en la posición ya deformada. Sin eso, los visemes abiertos se hundían en la cabeza y solo asomaban las comisuras.
- **Límite conocido:** el avatar es una cabeza estilizada de baja poligonía, sin dientes ni lengua; `FF` y `TH` se distinguen por apertura, no por contacto labiodental o dental. Se revisará si el criterio visual de la Fase 2 lo exige.
- **Límite conocido:** el e2e de Playwright sí levanta WebGL en headless con `--use-angle=swiftshader`; comprueba DOM, estado y ausencia de errores de consola, no la estética.
- **Entorno:** los subagentes del workflow estaban denegados en la sesión, así que spec, plan e implementación se ejecutaron inline en lugar de con implementer por tarea.
