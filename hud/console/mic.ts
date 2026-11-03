import {wsUrl} from './api';

const SAMPLE_RATE = 24_000; // Voice Transcribe PCM_24KHZ
const FRAME = (SAMPLE_RATE * 80) / 1000; // 80 ms per WebSocket frame

// Collects mono float samples off the audio thread and posts them in blocks.
const WORKLET = `
class Tap extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) this.port.postMessage(channel.slice(0));
    return true;
  }
}
registerProcessor('cueon-tap', Tap);
`;

export interface MicEvent {
  type: string;
  transcript?: string;
  final?: boolean;
  message?: string;
}

/** Streams the microphone as PCM16 24 kHz to the hub's /audio socket. Returns a stop function. */
export async function startMic(onEvent: (event: MicEvent) => void): Promise<() => void> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true},
  });
  // The context resamples the microphone to 24 kHz for us.
  const context = new AudioContext({sampleRate: SAMPLE_RATE});
  const url = URL.createObjectURL(new Blob([WORKLET], {type: 'application/javascript'}));
  await context.audioWorklet.addModule(url);
  URL.revokeObjectURL(url);

  const socket = new WebSocket(wsUrl('/audio'));
  socket.binaryType = 'arraybuffer';
  socket.onmessage = event => onEvent(JSON.parse(event.data));
  socket.onclose = () => onEvent({type: 'closed'});

  const source = context.createMediaStreamSource(stream);
  const tap = new AudioWorkletNode(context, 'cueon-tap');
  let pending = new Int16Array(FRAME);
  let filled = 0;
  tap.port.onmessage = ({data}: MessageEvent<Float32Array>) => {
    for (const sample of data) {
      const clamped = Math.max(-1, Math.min(1, sample));
      pending[filled++] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
      if (filled === FRAME) {
        if (socket.readyState === WebSocket.OPEN) socket.send(pending.buffer);
        pending = new Int16Array(FRAME);
        filled = 0;
      }
    }
  };
  source.connect(tap);

  return () => {
    source.disconnect();
    tap.disconnect();
    stream.getTracks().forEach(track => track.stop());
    void context.close();
    socket.close();
  };
}
