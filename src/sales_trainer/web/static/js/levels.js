 // levels.js — manejo de cards, gauge y report para /debug/levels
 //
 // 1. Al hacer click en una card, abrimos /ws/chat?session=<token>&level=<n>
 // 2. Escuchamos los mensajes del socket: transcript, turn_end, gauge, end, retry
 // 3. Actualizamos el canvas de gauge
 // 4. Al finalizar, mostramos el botón de retry y el modal de reporte

const WS_PATH = "/ws/chat";
const BASE_URL = location.origin;

const cards = document.querySelectorAll(".level-card");
const gaugeCanvas = document.getElementById("gauge-canvas");
const gaugeInfo = document.getElementById("gauge-info");
const retryBtn = document.getElementById("retry-btn");
const reportModal = document.getElementById("report-modal");
const reportText = document.getElementById("report-text");
const closeReport = document.getElementById("close-report");

let ws = null;
let currentLevel = null;
let conversationTurns = []; // array de objetos {user, assistant, temp, cause}
let lastTemperature = 50;

cards.forEach(card => {
  card.addEventListener("click", () => {
    const level = card.dataset.level;
    const name = card.dataset.name;
    currentLevel = level;

    // Genera un token simple y lo registra
    const token = "level-" + Date.now() + "-" + Math.random().toString(36).substr(2, 9);
    // Register session (el server hará el registro real al aceptar)
    const wsPath = `${WS_PATH}?session=${token}&level=${level}`;
    ws = new WebSocket(wsPath);

    ws.onopen = () => {
      console.log("WS opened for level", level);
    };

    ws.onmessage = (event) => {
      const msg = event.data;
      if (typeof msg === "string") {
        const data = JSON.parse(msg);
        handleSocketMessage(data);
      }
    };

    ws.onclose = () => {
      console.log("WS closed");
      ws = null;
    };

    ws.onerror = (err) => {
      console.error("WS error", err);
    };
  });
});

function handleSocketMessage(data) {
  const type = data.type;

  switch (type) {
    case "ready":
      // Show the conversation can start
      console.log("Ready", data.character);
      break;

    case "transcript":
      // Add user text to the turns array
      conversationTurns.push({user: data.text, assistant: null, temp: lastTemperature, cause: ""});
      break;

    case "gauge":
      // Update gauge UI
      lastTemperature = data.temperature;
      updateGauge(data.temperature, data.cause || "");
      conversationTurns[conversationTurns.length - 1].temp = data.temperature;
      conversationTurns[conversationTurns.length - 1].cause = data.cause || "";

      if (data.win) {
        showWin();
      } else if (data.lost) {
        showLost();
      }
      break;

    case "end":
      // Conversation finished (turns exhausted or temperature 0)
      console.log("End", data);
      showRetryButton(true);
      showReport(data);
      break;

    case "retry":
      // Restart conversation with same character
      console.log("Retry");
      resetConversation();
      break;
  }
}

function updateGauge(temp, cause) {
  const ctx = gaugeCanvas.getContext("2d");
  ctx.clearRect(0, 0, gaugeCanvas.width, gaugeCanvas.height);

  // Draw simple background
  ctx.fillStyle = "#fff";
  ctx.fillRect(20, 20, 160, 160);
  ctx.strokeStyle = "#000";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(100, 100, 80, 0, 2 * Math.PI);
  ctx.stroke();

  // Draw temperature bar (simple fill)
  const barWidth = (temp / 100) * 120;
  ctx.fillStyle = temp > 80 ? "#d00" : temp > 50 ? "#d90" : "#090";
  ctx.fillRect(70, 60, barWidth, 20);

  // Draw temperature text
  ctx.fillStyle = "#000";
  ctx.font = "bold 20px Arial";
  ctx.textAlign = "center";
  ctx.fillText(`${temp}°C`, 100, 95);

  // Show cause
  gaugeInfo.textContent = cause || "";
}

function showWin() {
  gaugeInfo.textContent = "¡Ganaste!";

  // Attempt to show report after a tiny setTimeout so the gauge has time to render
  setTimeout(() => showReportFromTurns(), 100);
  retryBtn.style.display = "inline-block";
}

function showLost() {
  gaugeInfo.textContent = "Perdiste (temperature 0)";
  retryBtn.style.display = "inline-block";
}

function showRetryButton(show) {
  retryBtn.style.display = show ? "inline-block" : "none";
}

function showReport(data) {
  // data can be the judge result object or the conversation turns
  let text;
  if (data && data.scores) {
    // Judge result object
    text = `Reporte de evaluación\n`;
    text += `Personaje: Level ${data.character.id} - ${data.character.name}\n`;
    text += `Temperatura final: ${data.temperature}°C\n`;
    text += `Causa: ${data.cause}\n`;
    text += `\nPuntuaciones por dimensión:\n`;
    for (const [dim, score] of Object.entries(data.scores)) {
      text += `  ${dim}: ${score}/10\n`;
    }
  } else {
    // Conversation turns
    text = `Reporte de la conversación\n`;
    text += `Nivel: ${currentLevel}\n`;
    text += `Turnos: ${conversationTurns.length}\n`;
    text += `Temperatura final: ${lastTemperature}°C\n`;
    text += `\nHistorial de turnos:\n`;
    conversationTurns.forEach((t, i) => {
      text += `  Turno ${i + 1}:\n`;
      text += `    Usuario: ${t.user || ""}\n`;
      text += `    Asistente: null\n`;
      text += `    Temperatura: ${t.temp}°C\n`;
      text += `    Causa: ${t.cause || ""}\n`;
    });
  }

  reportText.value = text;
  reportModal.style.display = "block";
}

function showReportFromTurns() {
  const text = `Reporte de la conversación\n`;
  text += `Nivel: ${currentLevel}\n`;
  text += `Turnos: ${conversationTurns.length}\n`;
  text += `Temperatura final: ${lastTemperature}°C\n`;
  text += `\nHistorial de turnos:\n`;
  conversationTurns.forEach((t, i) => {
    text += `  Turno ${i + 1}:\n`;
    text += `    Usuario: ${t.user || ""}\n`;
    text += `    Asistente: null\n`;
    text += `    Temperatura: ${t.temp}°C\n`;
    text += `    Causa: ${t.cause || ""}\n`;
  });
  reportText.value = text;
  reportModal.style.display = "block";
}

function resetConversation() {
  // Close existing WS if any
  if (ws) {
    ws.close();
    ws = null;
  }
  conversationTurns = [];
  lastTemperature = 50;
  gaugeInfo.textContent = "";
  gaugeCanvas.getContext("2d").clearRect(0, 0, gaugeCanvas.width, gaugeCanvas.height);
  showRetryButton(false);
  reportModal.style.display = "none";
}

closeReport.addEventListener("click", () => {
  reportModal.style.display = "none";
});

// Allow download of the report text
reportText.addEventListener("keydown", (e) => {
  if (e.key === "Ctrl" || e.key === "s") {
    // In a real app we'd trigger a real download blob;
    // for this demo we just alert
    alert("Reporte copiado al portapapeles (simulado)");
    e.preventDefault();
  }
});
