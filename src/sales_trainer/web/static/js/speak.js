// Pure timeline lookup: the last event at or before tMs, "sil" before the first
// event and when the timeline is empty. The player samples AudioContext.currentTime
// and asks this function, so the mouth never drifts with timer accumulation.
export function visemeAt(timeline, tMs) {
  let current = "sil";
  for (const event of timeline) {
    if (event.t_ms > tMs) break;
    current = event.viseme;
  }
  return current;
}

let audioContext = null;

function getAudioContext() {
  if (audioContext === null) {
    audioContext = new AudioContext();
  }
  return audioContext;
}

export async function speak(text, { onViseme = () => {}, onEnd = () => {} } = {}) {
  const response = await fetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) {
    throw new Error(`tts request failed: ${response.status}`);
  }
  const payload = await response.json();

  const raw = atob(payload.audio_base64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) {
    bytes[i] = raw.charCodeAt(i);
  }

  const context = getAudioContext();
  await context.resume();
  const buffer = await context.decodeAudioData(bytes.buffer);

  const source = context.createBufferSource();
  source.buffer = buffer;
  source.connect(context.destination);

  const startedAt = context.currentTime;
  const durationMs = buffer.duration * 1000;

  function tick() {
    const elapsedMs = (context.currentTime - startedAt) * 1000;
    if (elapsedMs > durationMs + 100) {
      return;
    }
    onViseme(visemeAt(payload.visemes, elapsedMs), elapsedMs);
    requestAnimationFrame(tick);
  }

  source.onended = () => onEnd();
  source.start(startedAt);
  requestAnimationFrame(tick);

  return { durationMs, timeline: payload.visemes };
}
