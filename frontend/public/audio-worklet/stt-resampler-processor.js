/**
 * Native Web Audio AudioWorkletProcessor for Real-Time STT.
 * Performs downsampling from arbitrary browser hardware rate (e.g. 48kHz, 44.1kHz)
 * to target 16,000 Hz, 16-bit linear PCM (S16LE) mono frames.
 * Emits 100ms PCM buffers (1,600 samples = 3,200 bytes) via Transferable ArrayBuffer.
 */
class STTResamplerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetSampleRate = 16000;
    this.sourceSampleRate = sampleRate; // Global AudioWorklet sampleRate
    this.resampleRatio = this.sourceSampleRate / this.targetSampleRate;
    this.chunkSampleCount = 1600; // 100ms at 16kHz
    this.outputBuffer = new Int16Array(this.chunkSampleCount);
    this.outputIndex = 0;
    this.fractionalOffset = 0;
    this.lastInputSample = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || input.length === 0) {
      return true;
    }

    const channelCount = input.length;
    const inputLength = input[0].length;
    if (inputLength === 0) {
      return true;
    }

    // Mixdown multi-channel to mono
    const mono = new Float32Array(inputLength);
    if (channelCount === 1) {
      mono.set(input[0]);
    } else {
      for (let i = 0; i < inputLength; i++) {
        let sum = 0;
        for (let ch = 0; ch < channelCount; ch++) {
          sum += input[ch][i];
        }
        mono[i] = sum / channelCount;
      }
    }

    // Fractional linear interpolation resampling
    let inIndex = this.fractionalOffset;

    while (inIndex < inputLength) {
      const idxFloor = Math.floor(inIndex);
      const frac = inIndex - idxFloor;

      const s0 = idxFloor === 0 ? this.lastInputSample : mono[idxFloor - 1];
      const s1 = mono[idxFloor];
      // Linear interpolation
      const interpolated = s0 + (s1 - s0) * frac;

      // Quantize Float32 [-1.0, 1.0] to Int16 linear PCM [-32768, 32767]
      let s = Math.max(-1.0, Math.min(1.0, interpolated));
      let int16Val = s < 0 ? Math.round(s * 32768) : Math.round(s * 32767);
      int16Val = Math.max(-32768, Math.min(32767, int16Val));

      this.outputBuffer[this.outputIndex++] = int16Val;

      // When 100ms chunk is filled, post buffer to main thread
      if (this.outputIndex >= this.chunkSampleCount) {
        const pcmBuffer = this.outputBuffer.slice();
        this.port.postMessage(pcmBuffer.buffer, [pcmBuffer.buffer]);
        this.outputIndex = 0;
      }

      inIndex += this.resampleRatio;
    }

    this.fractionalOffset = inIndex - inputLength;
    this.lastInputSample = mono[inputLength - 1];

    return true;
  }
}

registerProcessor("stt-resampler-processor", STTResamplerProcessor);
