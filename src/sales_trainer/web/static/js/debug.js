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
