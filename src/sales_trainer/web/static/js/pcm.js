// Pure PCM helpers shared by the audio worklet and the node test.

export function toPcm16(samples) {
  const out = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    out[i] = Math.round(clamped * 32767);
  }
  return out;
}

// Box-filter downsampling plus framing: every `ratio` input samples become one
// 16 kHz sample, and every `frameSize` of those becomes one Int16 chunk.
export class PcmFramer {
  constructor(ratio, frameSize = 512) {
    this.ratio = ratio;
    this.frameSize = frameSize;
    this.frame = new Float32Array(frameSize);
    this.filled = 0;
    this.sum = 0;
    this.count = 0;
  }

  push(sample) {
    this.sum += sample;
    this.count += 1;
    if (this.count < this.ratio) {
      return null;
    }
    this.frame[this.filled] = this.sum / this.ratio;
    this.filled += 1;
    this.sum = 0;
    this.count = 0;
    if (this.filled < this.frameSize) {
      return null;
    }
    this.filled = 0;
    return toPcm16(this.frame);
  }
}
