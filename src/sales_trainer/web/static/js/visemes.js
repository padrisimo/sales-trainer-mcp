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
