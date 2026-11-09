import { createScene } from "./scene.js";
import { speak } from "./speak.js";

const canvas = document.getElementById("avatar");
const input = document.getElementById("text");
const button = document.getElementById("speak");
const status = document.getElementById("status");

const scene = createScene(canvas);

const state = { ready: false, speaking: false, activeViseme: "sil", timelineLength: 0 };
window.ttsDebug = state;

button.addEventListener("click", async () => {
  if (state.speaking) {
    return;
  }
  state.speaking = true;
  status.textContent = "hablando";
  try {
    const result = await speak(input.value, {
      onViseme: (viseme) => {
        state.activeViseme = viseme;
        scene.avatar.group.userData.targetViseme = viseme;
      },
      onEnd: () => {
        state.speaking = false;
        state.activeViseme = "sil";
        scene.avatar.group.userData.targetViseme = "sil";
        status.textContent = "listo";
      },
    });
    state.timelineLength = result.timeline.length;
  } catch (error) {
    state.speaking = false;
    status.textContent = `error: ${error.message}`;
  }
});

requestAnimationFrame(() => {
  requestAnimationFrame(() => {
    state.ready = true;
  });
});
