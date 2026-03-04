import { useCallback, useRef } from "react";

const SAMPLE_RATE = 24000;

function base64ToInt16Array(base64: string): Int16Array {
  const binaryStr = atob(base64);
  const bytes = new Uint8Array(binaryStr.length);
  for (let i = 0; i < binaryStr.length; i++) {
    bytes[i] = binaryStr.charCodeAt(i);
  }
  return new Int16Array(bytes.buffer);
}

function int16ToFloat32(int16: Int16Array): Float32Array {
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32768;
  }
  return float32;
}

export function useAudioPlayer() {
  const ctxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const nextStartTimeRef = useRef(0);
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);

  const ensureContext = useCallback(() => {
    if (!ctxRef.current) {
      ctxRef.current = new AudioContext({ sampleRate: SAMPLE_RATE });
      analyserRef.current = ctxRef.current.createAnalyser();
      analyserRef.current.fftSize = 128;
      analyserRef.current.smoothingTimeConstant = 0.75;
      analyserRef.current.connect(ctxRef.current.destination);
    }
    if (ctxRef.current.state === "suspended") {
      ctxRef.current.resume();
    }
    return ctxRef.current;
  }, []);

  const playChunk = useCallback(
    (base64Data: string) => {
      const ctx = ensureContext();
      const int16 = base64ToInt16Array(base64Data);
      if (int16.length === 0) return;

      const float32 = int16ToFloat32(int16);
      const buffer = ctx.createBuffer(1, float32.length, SAMPLE_RATE);
      buffer.copyToChannel(new Float32Array(float32.buffer.slice(0)) as Float32Array<ArrayBuffer>, 0);

      const source = ctx.createBufferSource();
      source.buffer = buffer;
      // Route through analyser so the visualizer picks up live audio data
      source.connect(analyserRef.current!);

      const now = ctx.currentTime;
      const startAt = Math.max(now, nextStartTimeRef.current);
      source.start(startAt);
      nextStartTimeRef.current = startAt + buffer.duration;

      activeSourcesRef.current.push(source);
      source.onended = () => {
        activeSourcesRef.current = activeSourcesRef.current.filter(
          (s) => s !== source,
        );
      };
    },
    [ensureContext],
  );

  const stopAudio = useCallback(() => {
    for (const source of activeSourcesRef.current) {
      try {
        source.stop();
      } catch {
        /* already stopped or never started */
      }
    }
    activeSourcesRef.current = [];
    nextStartTimeRef.current = 0;
  }, []);

  const reset = useCallback(() => {
    nextStartTimeRef.current = 0;
  }, []);

  return { playChunk, reset, ensureContext, analyserRef, stopAudio };
}
