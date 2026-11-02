# Design — Fase 0: Esqueleto del MCP + FastAPI + navegador

- **Fecha:** 2026-11-03
- **Tema:** fase0-esqueleto
- **Estado:** Aprobado por el usuario

## Objetivo

Cumplir el criterio de la Fase 0 del proyecto Sales Trainer MCP:

> Desde opencode o Claude Code, una llamada a `sales_trainer_start` abre el navegador con una página y devuelve la URL.

## Criterio de aceptación

1. `sales_trainer_start(level, product_brief, language)` arranca el servidor web si no está activo.
2. Abre el navegador en `http://127.0.0.1:PORT/?session=<token>`.
3. Devuelve `{ url, session_id, ... }`.
4. `sales_trainer_status` / `sales_trainer_stop` operables (mínimo).

## Alcance

**In:**
- `src/sales_trainer/mcp_server.py`: FastMCP server, transporte stdio, tools `start` / `status` / `stop`.
- `src/sales_trainer/web/app.py`: app FastAPI.
- Bootstrap: uvicorn server en thread daemon.
- Bind `127.0.0.1`, puerto configurable (default 8765).
- Logging a stderr.

**Out (fases siguientes):**
- Avatar 3D, audio, STT/TTS, LLM, evaluación, DB, UI definitiva, WebSocket funcional.

## Enfoque y decisiones

- **Arranque del servidor web:** Opción A — uvicorn en thread daemon dentro del proceso MCP. Motivo: menor complejidad que gestionar subprocess en Fase 0; la memoria del proyecto contempla "arranca en un hilo o proceso hijo".
- **Placeholder web:** respuesta HTML mínima en `GET /` (se sustituirá por la UI real en Fase 6).
- **Puerto:** fijo por defecto 8765, configurable por variable de entorno.

## Detalles operativos

- Transporte MCP: stdio (stdout reservado al protocolo; logs a stderr).
- Sesión: token UUID en la URL.
- Browser: `webbrowser.open(url)`.

## Riesgos / límites

- Manejo del loop asyncio al arrancar uvicorn en thread (detalle de implementación, sin bloqueo de diseño).
- Sin WebSocket ni audio en Fase 0.

## Open questions

- Ninguna — diseño cerrado con la aprobación del usuario.
