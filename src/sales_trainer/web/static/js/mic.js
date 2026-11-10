// Microphone to websocket: PCM16 mono 16 kHz frames of 512 samples (32 ms).

export async function startListening({ session, onMessage, onError }) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
    },
  });

  const context = new AudioContext({ sampleRate: 16000 });
  await context.resume();
  await context.audioWorklet.addModule("/static/js/pcm-worklet.js");

  const source = context.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(context, "pcm-worklet");
  // A worklet with no path to the destination is not pulled by the graph.
  node.connect(context.destination);

  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(
    `${scheme}://${location.host}/ws/stt?session=${encodeURIComponent(session)}`,
  );
  socket.binaryType = "arraybuffer";

  socket.addEventListener("message", (event) => onMessage(JSON.parse(event.data)));
  socket.addEventListener("error", () => onError(new Error("websocket error")));

  node.port.onmessage = (event) => {
    if (socket.readyState === WebSocket.OPEN) {
      socket.send(event.data.buffer);
    }
  };
  source.connect(node);

  return {
    stop() {
      node.port.onmessage = null;
      source.disconnect();
      node.disconnect();
      socket.close();
      void context.close();
      for (const track of stream.getTracks()) {
        track.stop();
      }
    },
  };
}
