import {useEffect, useRef, useState} from 'react';

export type HudState = 'idle' | 'listening' | 'thinking' | 'card' | 'repeat' | 'present' | 'missed';

export interface CuePoint {
  text: string;
  done: boolean;
}

export interface HudMessage {
  type: 'hud';
  state: HudState;
  id?: string;
  partial?: string;
  question?: string;
  lead?: string;
  source?: string;
  /** 'bank' = prepared and checked card; 'live' = written on the spot by Spark. */
  path?: 'bank' | 'live';
  live?: boolean;
  /** Nearest prepared card shown while Spark is still writing. */
  tentative?: boolean;
  writing?: boolean;
  /** Which of several candidate cards this is (swipe left/right). */
  choice?: number;
  choices?: number;
  // Presentation mode
  page?: number;
  total?: number;
  title?: string;
  points?: string[] | CuePoint[];
  bridge?: string;
  missed?: string[];
  // Talk timer
  ends_at?: number;
  pages_left?: number;
  behind?: boolean;
  short?: string;
  /** Sent on (re)connect: the state was already on screen, so don't ack it as a new render. */
  replay?: boolean;
  /** Set by the hub once the card has been up long enough to read. */
  dimmed?: boolean;
}

const IDLE: HudMessage = {type: 'hud', state: 'idle'};

function hubUrl(): string | null {
  const fromQuery = new URLSearchParams(location.search).get('hub');
  if (fromQuery) return fromQuery;
  // Served by the hub at /glasses, or by the Vite dev server (which proxies /hud): same host.
  // Anywhere else (a static host such as Vercel) needs ?hub=wss://… to know where the hub is.
  if (location.pathname.startsWith('/glasses') || import.meta.env.DEV) {
    return `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/hud`;
  }
  return null;
}

/** Connects to the hub, reconnecting after drops. Returns the latest HUD message and a sender. */
export function useHub() {
  const [message, setMessage] = useState<HudMessage>(IDLE);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    let retry: number | undefined;

    const url = hubUrl();
    if (!url) return;

    const connect = () => {
      const socket = new WebSocket(url);
      socketRef.current = socket;
      socket.onopen = () => setConnected(true);
      socket.onmessage = event => {
        const data = JSON.parse(event.data) as HudMessage;
        if (data.type === 'hud') setMessage(data);
      };
      socket.onclose = () => {
        setConnected(false);
        if (!closed) retry = window.setTimeout(connect, 1000);
      };
    };

    connect();
    return () => {
      closed = true;
      window.clearTimeout(retry);
      socketRef.current?.close();
    };
  }, []);

  const send = (data: object) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(data));
  };

  return {message, connected, send};
}
