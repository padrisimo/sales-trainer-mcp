import * as THREE from "./vendor/three.module.js";
import { createAvatar } from "./avatar.js";
import { VISEMES } from "./visemes.js";

export function createScene(canvas, options = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x101418, 1);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
  camera.position.set(0, 0.02, 4.4);
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

    // Idle: never touches the viseme morph targets, so the debug panel stays in control.
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
