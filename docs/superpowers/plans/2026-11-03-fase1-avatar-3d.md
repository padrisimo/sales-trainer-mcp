# Fase 1: Avatar 3D procedural + `/debug/visemes` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-subagent-driven-development (recommended) or superpowers-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Servir una escena Three.js con una cabeza 3D procedural que expone los 15 morph targets de visema Oculus, con idle (parpadeo, respiración, micro-cabeza), y un panel `/debug/visemes` que aplica un viseme por botón.

**Architecture:** El build ESM de Three.js `0.187.0` (`three.module.js` + `three.core.js`, `three.module.js` importa `./three.core.js`) se versiona en `src/sales_trainer/web/static/js/vendor/` y FastAPI lo sirve con `StaticFiles` en `/static`, sin CDN. La cabeza se construye por código en `avatar.js`: primitivas de Three.js para cráneo, pelo, ojos y cejas, y un disco `CircleGeometry` para la boca al que se le generan 15 morph targets, uno por viseme, a partir de tres parámetros (`open`, `wide`, `round`). `scene.js` monta renderer, cámara, luces, idle y el bucle que interpola los pesos de los morph targets hacia el viseme activo.

**Tech Stack:** Python 3.11 + FastAPI 0.162 + uvicorn 0.54 (ya instalados), Three.js 0.187.0 vendorizado, JS ESM sin bundler, pytest + Playwright (python) para el e2e, ruff.

**Repositorio:** `/Users/adrian/Documents/Projects/sales-trainer-mcp`, rama `main`. Punto de partida: suite en `7 passed`, `ruff` limpio, `src/sales_trainer/web/app.py` sirviendo un `GET /` placeholder.

**Convenciones que no se pueden romper:** sin CDN en runtime; stdout reservado al protocolo MCP (por eso uvicorn y sus logs ya van a stderr en el thread del servidor); la boca **nunca** se anima por amplitud de audio ni de forma aleatoria.

---

## Task 1: Vendorizar Three.js

**Files:**
- Create: `package.json`
- Create: `package-lock.json` (generado por npm)
- Create: `src/sales_trainer/web/static/js/vendor/three.module.js`
- Create: `src/sales_trainer/web/static/js/vendor/three.core.js`
- Create: `src/sales_trainer/web/static/LICENSES.md`
- Modify: `.gitignore`

- [ ] **Step 1: Crear `package.json`**

Contenido completo de `package.json`:

```json
{
  "name": "sales-trainer-mcp-web",
  "private": true,
  "version": "0.0.0",
  "description": "JS vendorizado para la UI del Sales Trainer (sin CDN en runtime)",
  "dependencies": {
    "three": "0.187.0"
  }
}
```

- [ ] **Step 2: Instalar y comprobar la versión**

Run: `npm install --no-fund --no-audit`

Run: `node -p "require('./node_modules/three/package.json').version"`

Expected: exit code 0; salida `0.187.0`.

- [ ] **Step 3: Copiar los dos ficheros ESM al árbol de estáticos**

```bash
mkdir -p src/sales_trainer/web/static/js/vendor
cp node_modules/three/build/three.module.js src/sales_trainer/web/static/js/vendor/three.module.js
cp node_modules/three/build/three.core.js src/sales_trainer/web/static/js/vendor/three.core.js
```

- [ ] **Step 4: Verificar que el import interno se resuelve en local**

Run: `grep -c "from './three.core.js'" src/sales_trainer/web/static/js/vendor/three.module.js`

Expected: exit code 0; salida `1`.

Run: `grep -c "REVISION = '187'" src/sales_trainer/web/static/js/vendor/three.core.js`

Expected: exit code 0; salida `1`.

- [ ] **Step 5: Añadir `node_modules/` a `.gitignore`**

Editar `.gitignore`: añadir al final la línea

```
node_modules/
```

- [ ] **Step 6: Documentar la licencia y el origen**

Contenido completo de `src/sales_trainer/web/static/LICENSES.md`:

```markdown
# Licencias de assets y dependencias servidas al navegador

## Three.js 0.187.0

- Origen: paquete npm `three@0.187.0`, ficheros `build/three.module.js` y `build/three.core.js`.
- Licencia: MIT (`node_modules/three/LICENSE`).
- Motivo de versionarlo: la aplicación no puede cargar nada desde un CDN en tiempo de ejecución.

No hay modelos 3D externos: el avatar es procedural.
```

- [ ] **Step 7: Commit**

```bash
git add package.json package-lock.json .gitignore src/sales_trainer/web/static
git commit -m "chore: vendor three.js 0.187.0 for offline UI"
```

---

## Task 2: Test unitario de la ruta `/debug/visemes` (rojo)

**Files:**
- Create: `tests/unit/test_debug_visemes_route.py`

- [ ] **Step 1: Escribir el test que falla**

Contenido completo de `tests/unit/test_debug_visemes_route.py`:

```python
from fastapi.testclient import TestClient

from sales_trainer.web.app import app

client = TestClient(app)


def test_debug_visemes_returns_html() -> None:
    response = client.get("/debug/visemes")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "/static/js/debug.js" in response.text


def test_debug_visemes_includes_canvas_and_panel() -> None:
    response = client.get("/debug/visemes")
    assert 'id="avatar"' in response.text
    assert 'id="panel"' in response.text
```

- [ ] **Step 2: Ejecutar y ver el rojo**

Run: `uv run pytest tests/unit/test_debug_visemes_route.py -v`

Expected: FAIL — exit code 1; `assert 404 == 200` en `test_debug_visemes_returns_html`.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_debug_visemes_route.py
git commit -m "test: add failing test for debug visemes route"
```

---

## Task 3: Servir estáticos, `/` e `/debug/visemes`

**Files:**
- Modify: `src/sales_trainer/web/app.py`

- [ ] **Step 1: Sustituir el contenido de `src/sales_trainer/web/app.py`**

Contenido completo de `src/sales_trainer/web/app.py`:

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Sales Trainer")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _page(relative: str, session: str) -> HTMLResponse:
    html = (STATIC_DIR / relative).read_text(encoding="utf-8")
    return HTMLResponse(content=html.replace("__SESSION_TOKEN__", session), media_type="text/html")


@app.get("/")
async def root(session: str = "") -> HTMLResponse:
    return _page("index.html", session)


@app.get("/debug/visemes")
async def debug_visemes(session: str = "") -> HTMLResponse:
    return _page("debug/visemes.html", session)
```

- [ ] **Step 2: Crear los HTML mínimos para poder arrancar la app**

Contenido completo de `src/sales_trainer/web/static/index.html` (se completa en la Task 8, aquí solo desbloquea la ruta):

```html
<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <title>Sales Trainer</title>
  </head>
  <body>
    <p id="session">session: __SESSION_TOKEN__</p>
  </body>
</html>
```

Contenido completo de `src/sales_trainer/web/static/debug/visemes.html`:

```html
<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <title>Sales Trainer — visemes</title>
  </head>
  <body>
    <canvas id="avatar"></canvas>
    <div id="panel"></div>
    <script type="module" src="/static/js/debug.js"></script>
  </body>
</html>
```

- [ ] **Step 3: Ejecutar el test nuevo y los de la Fase 0**

Run: `uv run pytest tests/unit -v`

Expected: exit code 0; `6 passed` (4 de MCP + 2 de web: el de `/` sigue pasando porque `index.html` conserva el título «Sales Trainer» y el token, y los 2 nuevos de `/debug/visemes`).

- [ ] **Step 4: Commit**

```bash
git add src/sales_trainer/web/app.py src/sales_trainer/web/static/index.html src/sales_trainer/web/static/debug/visemes.html
git commit -m "feat: serve avatar pages and static files"
```

---

## Task 4: `visemes.js` — los 15 nombres y sus formas

**Files:**
- Create: `src/sales_trainer/web/static/js/visemes.js`

- [ ] **Step 1: Crear `visemes.js`**

Contenido completo de `src/sales_trainer/web/static/js/visemes.js`:

```javascript
// Conjunto interno de visemas Oculus. Estos 15 nombres son el contrato con la
// Fase 2 (fonemas -> visema) y con los morph targets de avatar.js.
export const VISEMES = [
  "sil",
  "PP",
  "FF",
  "TH",
  "DD",
  "kk",
  "CH",
  "SS",
  "nn",
  "RR",
  "aa",
  "E",
  "I",
  "O",
  "U",
];

// Forma de la boca por viseme: apertura, anchura y redondeo, de 0 a 1.
export const VISEME_SHAPES = {
  sil: { open: 0.0, wide: 0.5, round: 0.0 },
  PP: { open: 0.0, wide: 0.55, round: 0.0 },
  FF: { open: 0.12, wide: 0.6, round: 0.0 },
  TH: { open: 0.25, wide: 0.55, round: 0.0 },
  DD: { open: 0.32, wide: 0.6, round: 0.0 },
  kk: { open: 0.38, wide: 0.45, round: 0.0 },
  CH: { open: 0.22, wide: 0.4, round: 0.6 },
  SS: { open: 0.08, wide: 0.8, round: 0.0 },
  nn: { open: 0.14, wide: 0.45, round: 0.0 },
  RR: { open: 0.2, wide: 0.35, round: 0.7 },
  aa: { open: 1.0, wide: 0.6, round: 0.0 },
  E: { open: 0.55, wide: 0.95, round: 0.0 },
  I: { open: 0.35, wide: 0.85, round: 0.0 },
  O: { open: 0.65, wide: 0.3, round: 0.9 },
  U: { open: 0.3, wide: 0.2, round: 1.0 },
};

// Vector de pesos one-hot alineado con VISEMES.
export function weightsFor(name) {
  return VISEMES.map((viseme) => (viseme === name ? 1 : 0));
}
```

- [ ] **Step 2: Verificar la lista desde node**

Run:

```bash
node --input-type=module -e "
import { VISEMES } from './src/sales_trainer/web/static/js/visemes.js';
const expected = ['sil','PP','FF','TH','DD','kk','CH','SS','nn','RR','aa','E','I','O','U'];
console.log(JSON.stringify(VISEMES) === JSON.stringify(expected) ? 'visemes ok' : 'MISMATCH');
"
```

Expected: exit code 0; salida `visemes ok`.

- [ ] **Step 3: Commit**

```bash
git add src/sales_trainer/web/static/js/visemes.js
git commit -m "feat: add oculus viseme list and mouth shapes"
```

---

## Task 5: `avatar.js` — cabeza procedural con 15 morph targets

**Files:**
- Create: `src/sales_trainer/web/static/js/avatar.js`
- Create: `tests/js/avatar_smoke.mjs`
- Create: `tests/unit/test_avatar_js.py`

- [ ] **Step 1: Crear `avatar.js`**

Contenido completo de `src/sales_trainer/web/static/js/avatar.js`:

```javascript
import * as THREE from "./vendor/three.module.js";
import { VISEMES, VISEME_SHAPES } from "./visemes.js";

const MOUTH_RADIUS_X = 0.31;
const MOUTH_RADIUS_Y = 0.17;

// Disco elíptico base de la boca: el morph target de cada viseme deforma esta base.
function mouthBaseGeometry() {
  const geometry = new THREE.CircleGeometry(1, 24);
  const position = geometry.attributes.position;
  for (let i = 0; i < position.count; i += 1) {
    position.setXYZ(
      i,
      position.getX(i) * MOUTH_RADIUS_X,
      position.getY(i) * MOUTH_RADIUS_Y,
      0,
    );
  }
  return geometry;
}

function mouthShapeArray(base, shape) {
  const out = new Float32Array(base.length);
  const scaleX = (0.45 + shape.wide * 0.75) * (1 - shape.round * 0.35);
  const scaleY = 0.12 + shape.open * 1.5;
  for (let i = 0; i < base.length; i += 3) {
    out[i] = base[i] * scaleX;
    out[i + 1] = base[i + 1] * scaleY;
    out[i + 2] = base[i + 2] + shape.round * 0.08;
  }
  return out;
}

export function createAvatar(options = {}) {
  const { skin = 0xd9a37a, hair = 0x2b2b2b } = options;

  const group = new THREE.Group();
  const head = new THREE.Group();
  group.add(head);

  const skull = new THREE.Mesh(
    new THREE.SphereGeometry(1, 32, 24),
    new THREE.MeshStandardMaterial({ color: skin, roughness: 0.85 }),
  );
  skull.scale.set(0.95, 1.1, 0.9);
  head.add(skull);

  const hairMesh = new THREE.Mesh(
    new THREE.SphereGeometry(1.01, 32, 24, 0, Math.PI * 2, 0, Math.PI / 2),
    new THREE.MeshStandardMaterial({ color: hair, roughness: 1 }),
  );
  hairMesh.scale.set(0.96, 1.08, 0.91);
  hairMesh.position.y = 0.12;
  head.add(hairMesh);

  const eyes = [];
  for (const x of [-0.32, 0.32]) {
    const eye = new THREE.Mesh(
      new THREE.SphereGeometry(0.13, 20, 16),
      new THREE.MeshStandardMaterial({ color: 0xf7f7f7, roughness: 0.4 }),
    );
    eye.position.set(x, 0.14, 0.74);
    const pupil = new THREE.Mesh(
      new THREE.SphereGeometry(0.06, 16, 12),
      new THREE.MeshStandardMaterial({ color: 0x1d2733, roughness: 0.3 }),
    );
    pupil.position.z = 0.08;
    eye.add(pupil);
    head.add(eye);
    eyes.push(eye);
  }

  for (const x of [-0.31, 0.31]) {
    const brow = new THREE.Mesh(
      new THREE.BoxGeometry(0.32, 0.05, 0.06),
      new THREE.MeshStandardMaterial({ color: hair, roughness: 1 }),
    );
    brow.position.set(x, 0.4, 0.78);
    head.add(brow);
  }

  const mouthGeometry = mouthBaseGeometry();
  const base = mouthGeometry.attributes.position.array;
  mouthGeometry.morphAttributes.position = VISEMES.map((name) => {
    const attribute = new THREE.BufferAttribute(
      mouthShapeArray(base, VISEME_SHAPES[name]),
      3,
    );
    attribute.name = name;
    return attribute;
  });

  const mouth = new THREE.Mesh(
    mouthGeometry,
    new THREE.MeshStandardMaterial({
      color: 0x5a1420,
      roughness: 0.6,
      side: THREE.DoubleSide,
    }),
  );
  mouth.position.set(0, -0.34, 0.82);
  mouth.updateMorphTargets();
  head.add(mouth);

  group.userData.targetViseme = "sil";

  return { group, head, mouth, eyes };
}
```

- [ ] **Step 2: Crear el smoke test de node**

Contenido completo de `tests/js/avatar_smoke.mjs`:

```javascript
import { createAvatar } from "../../src/sales_trainer/web/static/js/avatar.js";
import { VISEMES, weightsFor } from "../../src/sales_trainer/web/static/js/visemes.js";

const expected = ["sil", "PP", "FF", "TH", "DD", "kk", "CH", "SS", "nn", "RR", "aa", "E", "I", "O", "U"];

if (JSON.stringify(VISEMES) !== JSON.stringify(expected)) {
  throw new Error(`viseme list mismatch: ${JSON.stringify(VISEMES)}`);
}

const avatar = createAvatar();
const names = Object.keys(avatar.mouth.morphTargetDictionary);

if (names.length !== 15) {
  throw new Error(`expected 15 morph targets, got ${names.length}`);
}
for (const name of expected) {
  if (!names.includes(name)) {
    throw new Error(`missing morph target: ${name}`);
  }
}

const influences = avatar.mouth.morphTargetInfluences;
if (influences.length !== 15) {
  throw new Error(`expected 15 morph influences, got ${influences.length}`);
}

const weights = weightsFor("aa");
if (weights.length !== 15 || weights[VISEMES.indexOf("aa")] !== 1) {
  throw new Error("weightsFor did not produce the expected one-hot vector");
}

console.log("avatar smoke ok");
```

- [ ] **Step 3: Ejecutar el smoke**

Run: `node tests/js/avatar_smoke.mjs`

Expected: exit code 0; salida `avatar smoke ok`.

- [ ] **Step 4: Envolverlo en un test de pytest**

Contenido completo de `tests/unit/test_avatar_js.py`:

```python
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_avatar_smoke_script_passes() -> None:
    result = subprocess.run(
        ["node", str(ROOT / "tests" / "js" / "avatar_smoke.mjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "avatar smoke ok" in result.stdout
```

- [ ] **Step 5: Ejecutar el test**

Run: `uv run pytest tests/unit/test_avatar_js.py -v`

Expected: exit code 0; `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/sales_trainer/web/static/js/avatar.js tests/js/avatar_smoke.mjs tests/unit/test_avatar_js.py
git commit -m "feat: add procedural avatar with 15 viseme morph targets"
```

---

## Task 6: `scene.js` — renderer, luces, idle y bucle

**Files:**
- Create: `src/sales_trainer/web/static/js/scene.js`

- [ ] **Step 1: Crear `scene.js`**

Contenido completo de `src/sales_trainer/web/static/js/scene.js`:

```javascript
import * as THREE from "./vendor/three.module.js";
import { createAvatar } from "./avatar.js";
import { VISEMES } from "./visemes.js";

export function createScene(canvas, options = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x101418, 1);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
  camera.position.set(0, 0.05, 3.4);
  camera.lookAt(0, 0, 0);

  scene.add(new THREE.HemisphereLight(0xffffff, 0x223344, 1.6));
  const key = new THREE.DirectionalLight(0xffffff, 2.2);
  key.position.set(1.6, 2.2, 2.4);
  scene.add(key);

  const avatar = createAvatar(options);
  scene.add(avatar.group);

  const clock = new THREE.Clock();
  let blinkCountdown = 2;
  let blinkAmount = 0;

  function resize() {
    const width = canvas.clientWidth || 640;
    const height = canvas.clientHeight || 480;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  function frame() {
    const dt = clock.getDelta();
    const t = clock.elapsedTime;

    // Idle: no toca los morph targets de visema, así el panel de depuración manda.
    avatar.head.position.y = Math.sin(t * 1.2) * 0.012;
    avatar.head.rotation.y = Math.sin(t * 0.5) * 0.07;
    avatar.head.rotation.x = Math.sin(t * 0.9) * 0.03;

    blinkCountdown -= dt;
    if (blinkCountdown <= 0) {
      blinkAmount = 1;
      blinkCountdown = 2.5 + (t % 1.7);
    }
    blinkAmount = Math.max(0, blinkAmount - dt * 8);
    const eyeScale = 1 - blinkAmount * 0.92;
    for (const eye of avatar.eyes) {
      eye.scale.y = eyeScale;
    }

    const target = avatar.group.userData.targetViseme;
    const influences = avatar.mouth.morphTargetInfluences;
    const blend = Math.min(1, dt * 12);
    for (let i = 0; i < VISEMES.length; i += 1) {
      const goal = VISEMES[i] === target ? 1 : 0;
      influences[i] += (goal - influences[i]) * blend;
    }

    renderer.render(scene, camera);
    requestAnimationFrame(frame);
  }

  resize();
  window.addEventListener("resize", resize);
  requestAnimationFrame(frame);

  return { renderer, scene, camera, avatar };
}
```

- [ ] **Step 2: Verificar que el módulo es sintácticamente válido**

Run: `node --input-type=module -e "import('./src/sales_trainer/web/static/js/scene.js').then(() => console.log('import ok')).catch((error) => { console.error(error.message); process.exit(1); })"`

Expected: exit code 0; salida `import ok`.

- [ ] **Step 3: Commit**

```bash
git add src/sales_trainer/web/static/js/scene.js
git commit -m "feat: add three.js scene with idle animation"
```

---

## Task 7: `debug.js` y las páginas HTML definitivas

**Files:**
- Create: `src/sales_trainer/web/static/js/debug.js`
- Modify: `src/sales_trainer/web/static/index.html`
- Modify: `src/sales_trainer/web/static/debug/visemes.html`

- [ ] **Step 1: Crear `debug.js`**

Contenido completo de `src/sales_trainer/web/static/js/debug.js`:

```javascript
import { createScene } from "./scene.js";
import { VISEMES } from "./visemes.js";

const canvas = document.getElementById("avatar");
const panel = document.getElementById("panel");
const status = document.getElementById("status");

const scene = createScene(canvas);

// Estado observable por el e2e: ready, active y la lista de visemes.
const state = { ready: false, active: "sil", visemes: VISEMES };
window.avatarDebug = state;

function select(name) {
  scene.avatar.group.userData.targetViseme = name;
  state.active = name;
  status.textContent = `viseme: ${name}`;
}

for (const name of VISEMES) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = name;
  button.dataset.viseme = name;
  button.addEventListener("click", () => select(name));
  panel.appendChild(button);
}

const reset = document.createElement("button");
reset.type = "button";
reset.textContent = "reset";
reset.dataset.viseme = "reset";
reset.addEventListener("click", () => select("sil"));
panel.appendChild(reset);

select("sil");

requestAnimationFrame(() => {
  requestAnimationFrame(() => {
    state.ready = true;
  });
});
```

- [ ] **Step 2: Escribir `index.html` definitivo**

Contenido completo de `src/sales_trainer/web/static/index.html`:

```html
<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Sales Trainer</title>
    <style>
      html,
      body {
        margin: 0;
        height: 100%;
        background: #101418;
        overflow: hidden;
      }
      #avatar {
        display: block;
        width: 100%;
        height: 100%;
      }
      #session {
        position: absolute;
        bottom: 8px;
        left: 8px;
        margin: 0;
        font: 12px system-ui, sans-serif;
        color: #46505c;
      }
    </style>
  </head>
  <body>
    <canvas id="avatar"></canvas>
    <p id="session">session: __SESSION_TOKEN__</p>
    <script type="module">
      import { createScene } from "/static/js/scene.js";
      createScene(document.getElementById("avatar"));
    </script>
  </body>
</html>
```

- [ ] **Step 3: Escribir `debug/visemes.html` definitivo**

Contenido completo de `src/sales_trainer/web/static/debug/visemes.html`:

```html
<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Sales Trainer — visemes</title>
    <style>
      html,
      body {
        margin: 0;
        height: 100%;
        background: #101418;
        color: #e6edf3;
        font: 13px system-ui, sans-serif;
      }
      body {
        display: grid;
        grid-template-columns: 1fr 260px;
      }
      #avatar {
        display: block;
        width: 100%;
        height: 100%;
      }
      #controls {
        padding: 12px;
        overflow-y: auto;
        background: #171d24;
      }
      #panel {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 6px;
        margin-bottom: 12px;
      }
      #panel button {
        padding: 8px 4px;
        border: 1px solid #2c3642;
        border-radius: 6px;
        background: #1f2833;
        color: inherit;
        cursor: pointer;
      }
      #panel button:hover {
        background: #2a3542;
      }
      #status {
        font-weight: 600;
      }
    </style>
  </head>
  <body>
    <canvas id="avatar"></canvas>
    <section id="controls">
      <p id="status">viseme: sil</p>
      <div id="panel"></div>
      <p>Pulsa un viseme para ver la forma de la boca. El idle sigue activo.</p>
    </section>
    <script type="module" src="/static/js/debug.js"></script>
  </body>
</html>
```

- [ ] **Step 4: Verificar las rutas y los estáticos desde Python**

Run:

```bash
uv run python -c "
from fastapi.testclient import TestClient
from sales_trainer.web.app import app
c = TestClient(app)
print('root', c.get('/').status_code)
print('debug', c.get('/debug/visemes').status_code)
print('three', c.get('/static/js/vendor/three.module.js').status_code)
print('core', c.get('/static/js/vendor/three.core.js').status_code)
print('debug.js', c.get('/static/js/debug.js').status_code)
"
```

Expected: exit code 0; `root 200`, `debug 200`, `three 200`, `core 200`, `debug.js 200`.

- [ ] **Step 5: Commit**

```bash
git add src/sales_trainer/web/static/js/debug.js src/sales_trainer/web/static/index.html src/sales_trainer/web/static/debug/visemes.html
git commit -m "feat: add avatar page and visemes debug panel"
```

---

## Task 8: E2E con Playwright

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/e2e/test_debug_visemes_page.py`

- [ ] **Step 1: Añadir Playwright a las dependencias de desarrollo**

En `pyproject.toml`, dentro de `[dependency-groups] dev`, añadir la línea:

```toml
    "playwright>=1.64.1",
```

Quedando:

```toml
[dependency-groups]
dev = [
    "pytest>=9.2.0",
    "pytest-asyncio>=1.4.1.post1",
    "ruff>=0.17.3",
    "playwright>=1.64.1",
]
```

- [ ] **Step 2: Instalar dependencias y el navegador**

Run: `uv sync`

Expected: exit code 0, sin errores.

Run: `uv run playwright install chromium`

Expected: exit code 0; descarga (o confirma ya instalado) Chromium. Es una descarga grande y solo ocurre una vez.

- [ ] **Step 3: Crear el test e2e**

Contenido completo de `tests/e2e/test_debug_visemes_page.py`:

```python
import subprocess
import time
import urllib.error
import urllib.request

import pytest
from playwright.sync_api import sync_playwright

PORT = 8124
BASE_URL = f"http://127.0.0.1:{PORT}"
VISEMES = [
    "sil",
    "PP",
    "FF",
    "TH",
    "DD",
    "kk",
    "CH",
    "SS",
    "nn",
    "RR",
    "aa",
    "E",
    "I",
    "O",
    "U",
]


def _wait_for_server(timeout_seconds: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = urllib.request.urlopen(f"{BASE_URL}/debug/visemes", timeout=2)
            try:
                if response.status == 200:
                    return
            finally:
                response.close()
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    raise RuntimeError("web server did not become ready in time")


@pytest.mark.e2e
def test_debug_page_applies_each_viseme() -> None:
    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "sales_trainer.web.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_server()
        errors: list[str] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
            )
            page = browser.new_page()

            def on_console(message) -> None:
                if message.type == "error":
                    errors.append(message.text)

            page.on("console", on_console)
            page.on("pageerror", lambda error: errors.append(str(error)))

            page.goto(f"{BASE_URL}/debug/visemes")
            page.wait_for_function("window.avatarDebug && window.avatarDebug.ready === true")

            buttons = page.locator("button[data-viseme]")
            assert buttons.count() == len(VISEMES) + 1

            for name in VISEMES:
                page.click(f'button[data-viseme="{name}"]')
                assert page.evaluate("window.avatarDebug.active") == name

            page.click('button[data-viseme="reset"]')
            assert page.evaluate("window.avatarDebug.active") == "sil"

            assert errors == []
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
```

- [ ] **Step 4: Ejecutar el e2e**

Run: `uv run pytest -m e2e -v`

Expected: exit code 0; `2 passed` (el smoke de la Fase 0 y el nuevo).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/e2e/test_debug_visemes_page.py
git commit -m "test: add e2e coverage for the visemes debug page"
```

---

## Task 9: Suite completa y linter

- [ ] **Step 1: Ejecutar toda la suite**

Run: `uv run pytest -v`

Expected: exit code 0; `10 passed`.

- [ ] **Step 2: Linter**

Run: `uv run ruff check .`

Expected: exit code 0; `All checks passed!`.

- [ ] **Step 3: Comprobación manual del criterio de fase**

Run: `uv run uvicorn sales_trainer.web.app:app --host 127.0.0.1 --port 8765`

Abrir `http://127.0.0.1:8765/debug/visemes` y pulsar los 15 botones.

Expected: la boca cambia de forma con cada viseme, el idle (parpadeo, respiración, micro-cabeza) sigue activo, y `sil` deja la boca cerrada. Parar con `Ctrl+C`.

---

## Task 10: Cerrar la fase

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/decisions.md`

- [ ] **Step 1: Actualizar el estado en `AGENTS.md`**

Antes:

```
- Fase actual: 1 (avatar 3D). En curso: avatar 3D con idle y panel `/debug/visemes`.
- Actualizar aquí al cerrar cada fase.
```

Después:

```
- Fase actual: 2 (TTS con visemas). En curso: TTS con línea temporal de visemas sincronizada.
- Actualizar aquí al cerrar cada fase.
```

- [ ] **Step 2: Añadir la decisión a `docs/decisions.md`**

Añadir al final del fichero:

```markdown
## 2026-11-03 — Fase 1: avatar procedural y Three.js vendorizado

- **Decisión:** el avatar de la Fase 1 se construye por código (primitivas de Three.js) con 15 morph targets de visema; no se usan modelos GLB/VRM.
- **Alternativa descartada:** empaquetar un modelo CC0 con morph targets Oculus o expresiones VRM.
- **Motivo:** cero riesgo de licencia, cero descargas en runtime, y los nombres de los morph targets son nuestros, que es el contrato que la Fase 2 necesita.
- **Three.js:** `0.187.0` versionado en `src/sales_trainer/web/static/js/vendor/` (`three.module.js` + `three.core.js`, el primero importa el segundo). Se sirve con `StaticFiles`; `node_modules/` está ignorado.
- **Límite conocido:** el avatar es una cabeza estilizada de baja poligonía, sin dientes ni lengua; `FF` y `TH` se distinguen por apertura, no por contacto labiodental o dental. Se revisará si el criterio visual de la Fase 2 lo exige.
- **Límite conocido:** si Chromium headless no levanta WebGL, el e2e cubre DOM y estado JS, y la comprobación visual queda como paso manual.
```

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md docs/decisions.md
git commit -m "docs: close out fase 1"
```

---

## Spec coverage

- Criterio 1 (`/debug/visemes` responde 200 text/html): Tasks 2-3, cubierto por `tests/unit/test_debug_visemes_route.py`.
- Criterio 2 (avatar visible y `window.avatarDebug` con viseme activo y lista): Tasks 6-7, verificado en el e2e de la Task 8.
- Criterio 3 (15 botones + reset, clic aplica viseme y actualiza el estado): Task 7 + e2e.
- Criterio 4 (nombres exactos de los 15 morph targets): Tasks 4-5, cubierto por `tests/js/avatar_smoke.mjs` vía `tests/unit/test_avatar_js.py`.
- Criterio 5 (idle sin intervención): Task 6, comprobación manual de la Task 9.
- Criterio 6 (sin CDN): Task 1 + `StaticFiles` de la Task 3, comprobado con las rutas de `/static` en la Task 7.
- Criterio 7 (ruff limpio y suite verde): Tasks 9.
- Non-goals respetados: no hay audio, ni `voice/visemes.py`, ni personajes, ni UI de sesión.

## Execution order

Cada task deja el repo en un estado verificable. Las Tasks 2-3 son rojo/verde de la ruta; las Tasks 4-7 construyen el frontend de abajo arriba (datos → geometría → escena → página); la Task 8 añade la comprobación real en navegador; las Tasks 9-10 cierran.
