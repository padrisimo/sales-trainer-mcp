import { startListening } from "./mic.js";

const status = document.getElementById("status");
const level = document.getElementById("level");
const turns = document.getElementById("turns");
const startButton = document.getElementById("start");
const stopButton = document.getElementById("stop");

const session = new URLSearchParams(window.location.search).get("session") ?? "";
const state = { ready: false, listening: false, turns: [], lastError: null };
window.sttDebug = state;

let connection = null;

function renderTurn(turn) {
  const item = document.createElement("li");
  const words = turn.words
    .map((word) => `${word.word} [${word.start_ms}-${word.end_ms} ms · ${word.probability.toFixed(2)}]`)
    .join(" ");
  item.textContent = turn.text;
  const detail = document.createElement("div");
  detail.className = "words";
  detail.textContent = words;
  item.append(detail);
  turns.prepend(item);
}

startButton.addEventListener("click", async () => {
  if (connection !== null) {
    return;
  }
  status.textContent = "conectando";
  try {
    connection = await startListening({
      session,
      onMessage: (message) => {
        if (message.type === "ready") {
          state.listening = true;
          status.textContent = "escuchando";
        } else if (message.type === "level") {
          level.value = message.probability;
        } else if (message.type === "turn_end") {
          level.value = 0;
          status.textContent = `turno de ${message.audio_ms} ms`;
        } else if (message.type === "transcript") {
          state.turns.push(message);
          renderTurn(message);
        } else if (message.type === "error") {
          state.lastError = message.message;
          status.textContent = `error: ${message.message}`;
        }
      },
      onError: (error) => {
        state.lastError = error.message;
        status.textContent = `error: ${error.message}`;
      },
    });
  } catch (error) {
    state.lastError = error.message;
    status.textContent = `error: ${error.message}`;
  }
});

stopButton.addEventListener("click", () => {
  if (connection !== null) {
    connection.stop();
    connection = null;
  }
  state.listening = false;
  level.value = 0;
  status.textContent = "parado";
});

requestAnimationFrame(() => {
  requestAnimationFrame(() => {
    state.ready = true;
  });
});
