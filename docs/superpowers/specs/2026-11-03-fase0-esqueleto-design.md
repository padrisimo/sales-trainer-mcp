# Design — Fase 0: Esqueleto del MCP + FastAPI + navegador

- **Fecha:** 2026-11-03
- **Tema:** fase0-esqueleto
- **Estado:** Aprobado por el usuario

## Context

El repositorio `sales-trainer-mcp` se encuentra en su fase inicial de materialización: todavía no contiene código fuente (no existen `src/`, `pyproject.toml`, `tests/`), solo la documentación de proyecto (`MEMORY.md`, `AGENTS.md`), la licencia y este spec.

`MEMORY.md` define el producto y la arquitectura prevista:

- Producto: entrenador de ventas por voz con avatar 3D, STT/TTS, LLM, evaluación y termómetro de temperatura.
- Arquitectura prevista:

```
opencode / Claude Code --stdio--> sales_trainer MCP server (FastMCP)
                                   | arranca en un hilo o proceso hijo
                                   v
                        FastAPI + uvicorn (127.0.0.1:PUERTO)
                                   | HTTP estático + WebSocket
                                   v
                Navegador: Three.js + AudioWorklet + UI
```

- Reglas innegociables: stdout reservado al protocolo MCP (los logs van a stderr o fichero); el servidor web solo se publica en `127.0.0.1`; token de sesión aleatorio en la URL con validación de `Origin`; versiones de dependencias fijadas; no inventar APIs; los pesos y personajes viven en YAML, no en código.

Los documentos de plan (`docs/PLAN.md`) y de decisiones (`docs/decisions.md`) aún no existen. El plan de trabajo distribuye el producto en fases; la Fase 0 es la primera entrega vertical y su criterio aprobado es: «desde opencode o Claude Code, una llamada a `sales_trainer_start` abre el navegador con una página y devuelve la URL».

## Goal

La Fase 0 del proyecto Sales Trainer MCP consiste en que, desde una sesión de opencode o Claude Code, invocar la herramienta MCP `sales_trainer_start` arranque el servidor web local si no está activo, abra el navegador en `http://127.0.0.1:PORT/?session=<token>` y devuelva `{ url, session_id }`, con las herramientas MCP `sales_trainer_status` y `sales_trainer_stop` operables como mínimo.

## Acceptance Criteria

1. `sales_trainer_start(level, product_brief, language)` arranca el servidor web si no está activo.
2. Abre el navegador en `http://127.0.0.1:PORT/?session=<token>`.
3. Devuelve `{ url, session_id }`.
4. `sales_trainer_status` / `sales_trainer_stop` operables (mínimo).

## Non-Goals

- Avatar 3D, audio, STT/TTS, LLM, evaluación, base de datos, UI definitiva y WebSocket funcional.
- Cualquier conversación o bucle de voz completo: el placeholder web no incluye avatar, audio ni reconocimiento de voz.
- Persistencia de sesiones o historial en esta fase.

## Proposed Architecture

- **Bootstrap del servidor web:** decisión aprobada, Opción A — el servidor web (FastAPI + uvicorn) arranca en un thread daemon dentro del mismo proceso que ejecuta el servidor MCP (FastMCP, transporte stdio). Motivo: menor complejidad de gestión que un proceso hijo en Fase 0; la memoria del proyecto contempla explícitamente «arranca en un hilo o proceso hijo».
- **Ubicación del bootstrap:** el thread daemon construye la aplicación FastAPI a partir de `src/sales_trainer/web/app.py` y arranca uvicorn sobre ella.
- **Bind y puerto:** `127.0.0.1`; puerto configurable mediante variable de entorno, con valor por defecto de `8765`.
- **Placeholder web:** respuesta HTML mínima en `GET /`; la UI real se sustituye en fases posteriores.
- **Transporte MCP:** stdio (FastMCP); stdout reservado al protocolo; logs a stderr.
- **Sesión:** token UUID incluido en la query string de la URL (`?session=<token>`).
- **Browser:** apertura mediante `webbrowser.open(url)`.

## Files To Change

- Create: `src/sales_trainer/mcp_server.py` — servidor MCP (FastMCP), transporte stdio, tools `start` / `status` / `stop`.
- Create: `src/sales_trainer/web/app.py` — aplicación FastAPI.
- Modify: ninguno en esta fase (el repositorio no contiene aún código fuente que editar).

## Testing Strategy

- La verificación de esta fase se apoya en la suite definida en `MEMORY.md`: tests unitarios, de integración y E2E con Playwright.
- En Fase 0 se verifica el comportamiento mínimo del esqueleto: que las tools `start` / `status` / `stop` entregan el payload esperado (`{ url, session_id }`) y que el servidor web responde en el placeholder de `GET /`.
- Los tests del flujo completo (avatar, audio, STT/TTS, LLM) quedan para fases posteriores y no forman parte de esta fase.

## Risks And Mitigations

1. **Manejo del loop asyncio al arrancar uvicorn en un thread:** la integración entre el loop del thread daemon y el servidor ASGI puede requerir configuración explícita. Mitigación: levantar el servidor con un event loop dedicado en el thread daemon; la alternativa de un proceso hijo queda registrada como opción de desescenario.
2. **Sin WebSocket ni audio en Fase 0:** el placeholder no incorpora funcionalidad conversacional. Mitigación: queda explícitamente fuera del alcance; las fases siguientes lo incorporan.

## Decision Summary

- Arranque del servidor web: **Opción A** — uvicorn en thread daemon dentro del proceso MCP.
- Bind: `127.0.0.1`; puerto por defecto `8765`, configurable por variable de entorno.
- Placeholder: respuesta HTML mínima en `GET /`; sustituida por la UI real en fases posteriores.
- Transporte MCP: stdio; logs a stderr.
- Sesión: token UUID en la URL.
- Browser: `webbrowser.open(url)`.

## Open Questions

- Ninguna — diseño cerrado con la aprobación del usuario («todo ok»).
