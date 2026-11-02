# Sales Trainer MCP — Prompt y memoria para opencode / Claude Code

*Entrenador de ventas con avatar 3D, voz en tiempo real y evaluación del discurso · Python · 2 de noviembre de 2026*

Cómo usarlo: la **Parte 1** es el prompt que pegas en opencode o Claude Code para que construya el proyecto por fases. La **Parte 2** es la memoria del proyecto (`AGENTS.md` para opencode, `CLAUDE.md` para Claude Code) que se guarda en la raíz del repositorio para que el agente conserve las reglas entre sesiones.

## Parte 1 — Prompt principal

### 1. Rol y objetivo

Actúa como ingeniero senior full-stack (Python + WebGL + audio en tiempo real). Construye desde cero un servidor MCP en Python llamado `sales-trainer-mcp`: un **entrenador de ventas por voz**. Cuando el usuario (desde opencode o Claude Code) invoca la herramienta de inicio, se abre una ventana del navegador con un **avatar 3D** que hace de potencial cliente. El usuario le habla por el micrófono, el avatar responde con voz sintetizada moviendo los labios con **visemas reales**, y el usuario debe **convencerle de que su producto le ahorrará tiempo y dinero**.

Se evalúan el contenido persuasivo, la **dicción**, la **entonación** y la **elocuencia**. Una UI muestra un **termómetro de temperatura del éxito** que sube o baja durante la conversación. Al terminar hay resultado, opciones para **reintentar** y un **informe descargable en texto** que explica qué fue bien y qué no.

### 2. Arquitectura y stack

Organiza el sistema así:

```
opencode / Claude Code --stdio--> sales_trainer MCP server (FastMCP)
                                   | arranca en un hilo o proceso hijo
                                   v
                        FastAPI + uvicorn (127.0.0.1:PUERTO)
                                   | HTTP estático + WebSocket
                                   v
                 Navegador: Three.js + AudioWorklet + UI
```

Regla crítica: con transporte stdio, **stdout está reservado al protocolo MCP**. Todos los logs van a stderr o a fichero.

Stack propuesto (verifica versiones actuales en la documentación oficial y fíjalas en `pyproject.toml`; si hay una alternativa claramente mejor, justifícala en `docs/decisions.md`):

- **MCP**: SDK oficial `mcp` (FastMCP), transporte stdio.
- **Backend**: FastAPI, uvicorn, WebSockets, pydantic v2, SQLite para el historial.
- **STT**: `faster-whisper` (modelo configurable, CPU int8 por defecto, GPU si existe) con timestamps y probabilidad por palabra. VAD con Silero.
- **Prosodia**: `parselmouth` (Praat) o `librosa` (pyin) para F0, intensidad y pausas.
- **TTS**: interfaz `TTSProvider` con dos implementaciones (ver sección 3).
- **LLM**: interfaz `LLMProvider` con Anthropic y cliente compatible con OpenAI (cubre Ollama, LM Studio, DeepSeek y similares), configurable por variables de entorno. Salidas estructuradas en JSON validadas con pydantic.
- **Frontend**: HTML + módulos JS sin framework pesado, Three.js (más `@pixiv/three-vrm` si se usan avatares VRM) y AudioWorklet. Dependencias JS fijadas y servidas en local: **sin CDN en tiempo de ejecución**, para que funcione offline.
- **Herramientas**: `uv`, `ruff`, `pytest`, `pytest-asyncio`, Playwright.

Estructura de carpetas objetivo:

```
sales-trainer-mcp/
  pyproject.toml, README.md, AGENTS.md / CLAUDE.md, .env.example
  config/scoring.yaml
  src/sales_trainer/
    mcp_server.py
    web/ (app.py, ws.py, static/ con index.html, js/, assets/)
    voice/ (stt.py, vad.py, prosody.py, visemes.py, tts/base.py, tts/azure.py, tts/local.py)
    llm/ (base.py, anthropic.py, openai_compat.py)
    characters/ (nivel1.yaml, nivel2.yaml, nivel3.yaml, prompts/)
    scoring/ (judge.py, delivery.py, temperature.py)
    reports/ (builder.py)
    storage/db.py
  tests/ (unit/, integration/, e2e/)
  docs/ (PLAN.md, decisions.md)
```

### 3. Voz: STT, TTS y visemas reales

**Captura de audio (navegador → servidor)**

- `getUserMedia` con `echoCancellation` y `noiseSuppression` activados.
- AudioWorklet que convierte a PCM16 mono a 16 kHz y lo envía por WebSocket en tramas binarias de 20–30 ms.
- VAD en el servidor para segmentar turnos: el turno termina tras unos 700 ms de silencio (configurable). Modo alternativo de pulsar para hablar. Entrada de texto de respaldo para depurar.
- **Barge-in**: si el usuario habla mientras el avatar habla, se corta el audio del avatar y se registra una interrupción.
- El audio crudo **no se guarda** salvo que `SAVE_AUDIO=true`.

**STT**

- Transcribe con timestamps por palabra y probabilidad por palabra. Guarda por turno: texto, palabras con probabilidad, duración, métricas de prosodia.

**TTS con visemas reales**

- Cada réplica del avatar produce **audio + línea temporal de visemas**: `[{t_ms, viseme, weight}]`.
- «Reales» significa derivados de los **fonemas realmente pronunciados con sus tiempos reales en el audio**. Está prohibido animar la boca con la amplitud del audio o con movimiento aleatorio.
- Conjunto interno de visemas: los 15 de Oculus (`sil, PP, FF, TH, DD, kk, CH, SS, nn, RR, aa, E, I, O, U`). Implementa tablas de mapeo desde los IDs de viseme de Azure (0–21) y desde fonemas IPA/espeak del español.
- Aplica coarticulación (interpolación y suavizado entre visemas) y cierre de boca en los silencios.
- **Proveedor A, Azure Speech**: emite eventos de visema con offsets de audio de forma nativa. Es la opción de máxima calidad y requiere clave.
- **Proveedor B, local y offline** (Piper o Kokoro u otro motor): obtén fonemas con duraciones si la librería los expone; si no, aplica *forced alignment* sobre el audio generado (por ejemplo `ctc-forced-aligner`, Montreal Forced Aligner o WhisperX) y convierte fonema → viseme. **Antes de decidir, investiga en la documentación actual qué expone cada librería y qué hay para español**, y documenta la decisión y sus límites en `docs/decisions.md`. Este es el punto técnico más delicado del proyecto: valídalo primero con un prototipo.
- **Sincronización**: el cliente reproduce con Web Audio y usa `AudioContext.currentTime` como reloj maestro. Desfase máximo tolerado: 40 ms.
- **Latencia objetivo**: menos de 2,5 s desde que el usuario termina de hablar hasta el primer audio del avatar. Para lograrlo: LLM en streaming y TTS por frases.
- Idioma por defecto español de España (`es-ES`), configurable. Voces y reglas de fonemas por idioma.

### 4. Avatar 3D

- Three.js con modelos GLB o VRM. Deben tener morph targets de visemas Oculus, o expresiones VRM (`aa, ih, ou, ee, oh`) con una tabla de mapeo a nuestros visemas.
- Animación idle: parpadeo, respiración, micromovimientos de cabeza y mirada.
- Reacción al estado del termómetro: interés alto → sonríe, asiente, se inclina hacia delante; interés bajo → gesto serio, mirada desviada, brazos cruzados o mirada al reloj.
- **Tres avatares distintos**, uno por personaje. No uses assets con licencia dudosa: modelos CC0 o propios, o avatares procedurales de baja poligonía con los mismos morph targets. Registra las licencias en `assets/LICENSES.md`.
- Página de depuración `/debug/visemes` con un botón por viseme y una frase de prueba para verificar la sincronía labial.

### 5. Personajes y niveles de dificultad

Cada personaje es una ficha YAML en `characters/` (personalidad, contexto de empresa, objeciones típicas, *hot buttons* que lo calientan o enfrían, muletillas propias, voz TTS, avatar, parámetros numéricos) con su prompt de sistema en un fichero aparte y versionado. Los nombres son sugerencias y se pueden cambiar.

- **Nivel 1 — Fácil: Marta Ruiz, directora de operaciones receptiva.** Temperatura inicial 50, umbral de éxito 75, máximo 10 turnos. Paciente y curiosa, hace preguntas razonables y da señales de compra. Perdona un discurso algo desordenado, pero premia los datos concretos.
- **Nivel 2 — Medio: Javier Soto, gerente neutral y escéptico.** Inicio 30, umbral 80, máximo 10 turnos. Plantea objeciones típicas (precio, «ya tengo proveedor», «no tengo tiempo para cambiar de sistema»). Pide ejemplos y cifras. Se enfría con vaguedades.
- **Nivel 3 — Difícil: Carmen Valdés, directora financiera sin interés.** Inicio 10, umbral 85, máximo 8 turnos. Dice que solo tiene dos minutos, interrumpe y responde seco. Se enfría con tópicos, muletillas, monotonía y discursos largos. Solo se calienta con propuestas cuantificadas (horas por semana, euros al mes, ROI, plazo de retorno), prueba social creíble y buenas preguntas de descubrimiento. Si la temperatura llega a 0, cuelga.

Reglas para el LLM que interpreta al personaje:

- Nunca sale del rol y nunca revela la puntuación ni la temperatura.
- Responde en lenguaje hablado: 1–3 frases cortas (menos de 45 palabras en el nivel 3).
- No sabe nada del producto más allá de lo que el vendedor le ha dicho.
- El producto lo define el usuario en un formulario previo (nombre, qué hace, precio, tres beneficios). Hay un producto demo por defecto.

### 6. Motor de evaluación y termómetro

Cada turno del usuario se evalúa en **dos capas independientes**.

**A) Contenido y persuasión (LLM como juez).** Llamada **separada** de la del personaje, para que el rol no contamine la evaluación. El juez recibe la transcripción, el brief del producto y una rúbrica, y devuelve JSON estricto con puntuaciones de 0 a 10 en:

- propuesta de valor;
- ahorro de tiempo cuantificado;
- ahorro de dinero cuantificado;
- manejo de objeciones;
- preguntas y personalización;
- estructura y claridad;
- cierre o llamada a la acción;
- recursos persuasivos (historia, prueba social, contraste antes/después, cifras).

**B) Entrega (señales medidas, nunca inventadas por el LLM).**

- **Dicción**: media y porcentaje de palabras con baja probabilidad en Whisper; velocidad de articulación.
- **Entonación**: variación de F0 (desviación típica en semitonos y rango), índice de monotonía, dinámica de intensidad, contorno en los finales de frase.
- **Ritmo y fluidez**: palabras por minuto (ideal 130–160), pausas de más de 1,5 s, muletillas por minuto (lista por idioma), repeticiones y falsos comienzos.
- **Elocuencia**: diversidad léxica y longitud media de frase, combinadas con los recursos persuasivos detectados por el juez.

Pesos y umbrales en `config/scoring.yaml`, **por nivel** (el nivel 3 pondera más la cuantificación y la entrega).

**Temperatura (0–100).** Por turno:

- `delta = (puntuación_turno − 50) / 50 × sensibilidad_personaje × delta_máximo`, con `delta_máximo` de ±15 por turno;
- inercia con media móvil para evitar saltos bruscos;
- bonificaciones por *hot buttons* acertados y penalizaciones por divagar, muletillas excesivas o interrumpir al cliente.

Cada cambio de temperatura se guarda con su causa en lenguaje natural (por ejemplo: «−8: afirmación genérica sin cifras»), para poder mostrarla en la UI y en el informe.

**Fin de la partida.** Victoria: alcanzar el umbral y mantenerlo dos turnos, o que el personaje acepte un siguiente paso concreto. Derrota: temperatura 0 (cuelga), turnos agotados o tiempo agotado.

### 7. Flujo de la UI, reintentos e informes

**Pantalla de inicio**

- Tres tarjetas de nivel con personaje, dificultad y consejos.
- Formulario del producto.
- Test de micrófono con medidor de nivel y gestión de permisos.

**Pantalla de sesión**

- Avatar centrado y subtítulos opcionales.
- Botón de micrófono o pulsar para hablar.
- **Termómetro vertical animado** con marca del umbral y zonas fría, templada y caliente.
- Contador de turnos y de tiempo.
- Indicadores discretos en vivo: ritmo, volumen y muletillas.
- Botón para terminar.

**Pantalla de resultado**

- Éxito o fracaso, gráfico de temperatura por turno y puntuación por dimensión.
- Tres puntos fuertes y tres a mejorar.
- Botones: **Reintentar mismo nivel**, **Cambiar de nivel o personaje**, **Descargar informe (.txt)** y **Ver historial**.

**Informe `.txt`** (UTF-8, legible en cualquier editor, sin depender de Markdown). Se genera siempre, y cuando la partida se pierde pone el foco en **por qué no funcionó**. Contenido:

- cabecera: fecha, nivel, personaje, producto, duración, resultado y temperatura final;
- evolución de la temperatura por turno con barra ASCII;
- puntuación por dimensión con su explicación;
- transcripción completa con marcas de tiempo;
- anotaciones por turno (qué ayudó y qué enfrió);
- momentos críticos;
- métricas de voz;
- plan de mejora con tres acciones concretas y reformulaciones sugeridas de las frases más débiles.

Endpoint: `GET /api/sessions/{id}/report.txt` con `Content-Disposition: attachment`.

**Historial** en SQLite, con comparación entre intentos del mismo nivel (mejora por dimensión).

### 8. Herramientas MCP

- `sales_trainer_start(level: 1|2|3, product_brief: str | None, language: str = "es")`: arranca el servidor web si no está activo, abre el navegador y devuelve la URL y el `session_id`.
- `sales_trainer_status(session_id)`: estado, turno actual y temperatura.
- `sales_trainer_get_report(session_id)`: devuelve el informe de texto y la ruta del fichero.
- `sales_trainer_list_sessions(limit)`: historial resumido.
- `sales_trainer_stop()`: cierra el servidor web.

Cada herramienta con descripción clara, esquema de entrada tipado y errores legibles.

### 9. Configuración, instalación y seguridad

- `.env.example` documentado: proveedor y modelo de LLM, claves, proveedor TTS, modelo Whisper, puerto, idioma y `SAVE_AUDIO`.
- Registro en **opencode** (`opencode.json`):

```json
{
  "mcp": {
    "sales-trainer": {
      "type": "local",
      "command": ["uv", "run", "sales-trainer-mcp"],
      "enabled": true
    }
  }
}
```

- Registro en **Claude Code**: `claude mcp add sales-trainer -- uv run sales-trainer-mcp`.
- Servidor web solo en `127.0.0.1`, token de sesión aleatorio en la URL y validación de `Origin` en el WebSocket.
- Todo el procesamiento es local por defecto; solo se usa la nube si el usuario configura claves de proveedores cloud.

### 10. Calidad y pruebas

- **Unitarias**: tablas de visemas, motor de temperatura (con puntuaciones simuladas, deterministas), métricas de prosodia con audios sintéticos, generador de informes y validación de las fichas YAML.
- **Integración**: WebSocket con audio de ejemplo → transcripción → respuesta con LLM simulado.
- **E2E con Playwright** (Chromium con micrófono falso: `--use-fake-device-for-media-stream` y `--use-file-for-fake-audio-capture=<wav>`), con proveedores LLM y TTS simulados: flujo completo del nivel 1 hasta la descarga del informe.
- **Proveedores mock** para ejecutar todo sin claves ni red.
- `ruff` y *type hints* en todo el código. README con instalación en cinco pasos y sección de resolución de problemas (permisos de micrófono, puertos, modelos).

### 11. Cómo trabajar

1. Empieza escribiendo `docs/PLAN.md` con arquitectura, decisiones y riesgos (sobre todo los visemas locales). Solo te detienes a preguntar ante un bloqueo real; en el resto de dudas, elige la opción más simple que cumpla los criterios y regístrala en `docs/decisions.md`.
2. Trabaja en fases verticales, con un commit por fase y los tests en verde antes de pasar a la siguiente:
   - **Fase 0**: esqueleto del MCP, FastAPI y apertura del navegador. Criterio: `sales_trainer_start` abre una página y devuelve la URL.
   - **Fase 1**: avatar 3D con idle y panel `/debug/visemes`. Criterio: cada viseme se ve correcto.
   - **Fase 2**: TTS con línea temporal de visemas sincronizada. Criterio: una frase en español se pronuncia con labios coherentes, desfase ≤ 40 ms.
   - **Fase 3**: micrófono, VAD y STT con timestamps y probabilidades. Criterio: transcripción correcta en español con turnos bien segmentados.
   - **Fase 4**: personajes con LLM y bucle de conversación con barge-in.
   - **Fase 5**: motor de evaluación (juez + entrega) y temperatura.
   - **Fase 6**: UI completa (niveles, termómetro, resultado, reintento).
   - **Fase 7**: informes `.txt`, historial y herramientas MCP restantes.
   - **Fase 8**: pruebas E2E, README, pulido y rendimiento.
3. No inventes APIs: lee la documentación actual de cada librería y fija versiones. Al terminar cada fase, actualiza la sección «Estado» de la memoria del proyecto.

### 12. Criterios de aceptación

- Desde opencode o Claude Code, una llamada a `sales_trainer_start` abre el navegador y permite una conversación hablada completa.
- Los labios siguen los fonemas reales del audio (sin animación por amplitud) con desfase ≤ 40 ms.
- Los tres niveles se comportan de forma claramente distinta y el nivel 3 es difícil de ganar sin cifras ni buena entrega.
- El termómetro reacciona turno a turno y cada cambio tiene una causa explicada.
- Tras ganar o perder, se puede reintentar y descargar el informe `.txt`.
- Toda la suite de pruebas pasa sin claves ni red, y existe al menos un E2E del flujo completo.