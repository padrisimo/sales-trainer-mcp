import * as THREE from "./vendor/three.module.js";
import { VISEMES, VISEME_SHAPES } from "./visemes.js";

const MOUTH_RADIUS_X = 0.31;
const MOUTH_RADIUS_Y = 0.17;
// El cráneo es una esfera escalada; la boca se curva para no quedar enterrada en ella.
const SKULL_SCALE = { x: 0.95, y: 1.1, z: 0.9 };
const SKULL_RADIUS = 1;
const MOUTH_CENTER = { y: -0.32, z: 0.88 };

function skullSurfaceZ(x, y) {
  const nx = x / SKULL_SCALE.x;
  const ny = (y - MOUTH_CENTER.y) / SKULL_SCALE.y;
  const squared = 1 - nx * nx - ny * ny;
  return SKULL_RADIUS * SKULL_SCALE.z * Math.sqrt(Math.max(0, squared));
}

// Disco elíptico base de la boca: el morph target de cada viseme deforma esta base.
function mouthBaseGeometry() {
  const geometry = new THREE.CircleGeometry(1, 24);
  const position = geometry.attributes.position;
  for (let i = 0; i < position.count; i += 1) {
    const x = position.getX(i) * MOUTH_RADIUS_X;
    const y = position.getY(i) * MOUTH_RADIUS_Y;
    const z = skullSurfaceZ(x, y) - MOUTH_CENTER.z + 0.01;
    position.setXYZ(i, x, y, z);
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
    new THREE.SphereGeometry(1.02, 32, 24, 0, Math.PI * 2, 0, Math.PI / 2.6),
    new THREE.MeshStandardMaterial({ color: hair, roughness: 1 }),
  );
  hairMesh.scale.set(0.96, 1.08, 0.91);
  hairMesh.position.y = 0.3;
  head.add(hairMesh);

  const eyes = [];
  for (const x of [-0.32, 0.32]) {
    const eye = new THREE.Mesh(
      new THREE.SphereGeometry(0.13, 20, 16),
      new THREE.MeshStandardMaterial({ color: 0xf7f7f7, roughness: 0.4 }),
    );
    eye.position.set(x, 0.1, 0.76);
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
    brow.position.set(x, 0.34, 0.83);
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
  mouth.position.set(0, MOUTH_CENTER.y, MOUTH_CENTER.z);
  mouth.updateMorphTargets();
  head.add(mouth);

  group.userData.targetViseme = "sil";

  return { group, head, mouth, eyes };
}
