# Licenses of assets and dependencies served to the browser

## Three.js 0.187.0

- Origen: paquete npm `three@0.187.0`, ficheros `build/three.module.js` y `build/three.core.js`.
- Licencia: MIT (`node_modules/three/LICENSE`).
- Reason for versioning it: the application cannot load anything from a CDN at runtime.

There are no external 3D models: the avatar is procedural.

## Silero VAD v5 (ONNX)

- Origin: `silero_vad/data/silero_vad.onnx` from the PyPI wheel `silero-vad==5.1.2` (project `snakers4/silero-vad`), SHA-256 `2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f`.
- License: MIT (shipped inside the wheel as `silero_vad-5.1.2.dist-info/licenses/LICENSE`).
- It is never served to the browser: `sales_trainer.voice.vad` loads it from `src/sales_trainer/voice/models/silero_vad.onnx`.
- Reason for versioning it: the `silero-vad` package would pull `torch` (~2.5 GB) for a 2.2 MB model; `onnxruntime` is already installed by `faster-whisper`.
