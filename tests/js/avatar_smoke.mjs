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

// Regresión: la boca (y cada morph target) debe quedar delante del cráneo, no dentro.
const SKULL = { x: 0.95, y: 1.1, z: 0.9 };
const MOUTH_Y = avatar.mouth.position.y;
const MOUTH_Z = avatar.mouth.position.z;

function skullSurfaceZ(x, y) {
  const squared = 1 - (x / SKULL.x) ** 2 - ((y - MOUTH_Y) / SKULL.y) ** 2;
  return SKULL.z * Math.sqrt(Math.max(0, squared));
}

const targets = [avatar.mouth.geometry.attributes.position, ...avatar.mouth.geometry.morphAttributes.position];
for (const target of targets) {
  for (let i = 0; i < target.count; i += 1) {
    const x = target.getX(i);
    const y = target.getY(i);
    const z = MOUTH_Z + target.getZ(i);
    if (z < skullSurfaceZ(x, y) - 0.005) {
      throw new Error(`mouth vertex ${i} of ${target.name || "base"} is inside the skull`);
    }
  }
}

console.log("avatar smoke ok");
