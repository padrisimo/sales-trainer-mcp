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
