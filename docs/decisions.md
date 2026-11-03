# Decisiones del proyecto

## 2026-11-03 — Fase 0: arranque del servidor web (esqueleto)

- **Decisión:** el servidor web (FastAPI + uvicorn) arranca en un thread daemon dentro del proceso MCP (SDK `mcp`, clase `MCPServer`, transporte stdio).
- **Alternativa descartada:** proceso hijo del MCP.
- **Motivo:** menor complejidad de gestión en Fase 0; la memoria del proyecto contempla «arranca en un hilo o proceso hijo».
- **Consecuencias:** el thread daemon construye la app FastAPI desde `src/sales_trainer/web/app.py` y arranca uvicorn sobre ella; bind `127.0.0.1`, puerto por defecto `8765` configurable con `SALES_TRAINER_PORT`.
- **Desvío del plan:** `uv_build` deriva el módulo del nombre del proyecto (`sales_trainer_mcp`); se fija `[tool.uv.build-backend] module-name = "sales_trainer"` en `pyproject.toml` para mantener el layout `src/sales_trainer/` de la memoria.
- **Límite conocido:** `sales_trainer_start` no valida `Origin` todavía porque no hay WebSocket; llega en la fase de audio.
