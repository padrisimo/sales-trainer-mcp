import { PcmFramer, toPcm16 } from "../../src/sales_trainer/web/static/js/pcm.js";

function expect(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${expected}, got ${actual}`);
  }
}

// 16 kHz: one input sample per output sample.
const framer16 = new PcmFramer(1);
const frames16 = [];
for (let i = 0; i < 512; i += 1) {
  const frame = framer16.push(i / 512);
  if (frame) {
    frames16.push(frame);
  }
}
expect(frames16.length, 1, "one frame per 512 samples at 16 kHz");
expect(frames16[0].length, 512, "frame length");
expect(frames16[0][0], 0, "first sample");
expect(frames16[0][511], Math.round((511 / 512) * 32767), "last sample");

// 48 kHz: three input samples average into one output sample.
const framer48 = new PcmFramer(3);
let produced = 0;
for (let i = 0; i < 512 * 3 - 1; i += 1) {
  if (framer48.push(0.5)) {
    produced += 1;
  }
}
expect(produced, 0, "no frame before 1536 input samples");
const frame48 = framer48.push(0.5);
expect(frame48 === null ? 0 : frame48.length, 512, "frame after 1536 input samples");
expect(frame48[0], Math.round(0.5 * 32767), "averaged value");
expect(frame48[511], Math.round(0.5 * 32767), "averaged last value");

// Clipping keeps a loud sample inside the PCM16 range.
const clipped = toPcm16(new Float32Array([2, -2, 0]));
expect(clipped[0], 32767, "clip high");
expect(clipped[1], -32767, "clip low");
expect(clipped[2], 0, "silence");

console.log("pcm downsample ok");
