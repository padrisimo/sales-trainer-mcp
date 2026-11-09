import { visemeAt } from "../../src/sales_trainer/web/static/js/speak.js";

const timeline = [
  { t_ms: 0, viseme: "sil", weight: 1 },
  { t_ms: 100, viseme: "aa", weight: 1 },
  { t_ms: 300, viseme: "PP", weight: 1 },
];

function expect(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${expected}, got ${actual}`);
  }
}

expect(visemeAt([], 0), "sil", "empty timeline");
expect(visemeAt(timeline, 0), "sil", "first event");
expect(visemeAt(timeline, 99), "sil", "just before the change");
expect(visemeAt(timeline, 100), "aa", "exact boundary");
expect(visemeAt(timeline, 299), "aa", "inside a segment");
expect(visemeAt(timeline, 300), "PP", "second boundary");
expect(visemeAt(timeline, 99999), "PP", "holds until the end");

console.log("viseme timeline ok");
