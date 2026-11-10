import { PcmFramer } from "./pcm.js";

class PcmWorklet extends AudioWorkletProcessor {
  constructor() {
    super();
    // The page asks for a 16 kHz context; if the browser ignores it, average down.
    this.framer = new PcmFramer(Math.max(1, Math.round(sampleRate / 16000)));
  }

  process(inputs) {
    const channel = inputs[0][0];
    if (channel) {
      for (let i = 0; i < channel.length; i += 1) {
        const frame = this.framer.push(channel[i]);
        if (frame) {
          this.port.postMessage(frame);
        }
      }
    }
    return true;
  }
}

registerProcessor("pcm-worklet", PcmWorklet);
