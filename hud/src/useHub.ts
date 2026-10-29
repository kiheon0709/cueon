import {useEffect, useRef, useState} from 'react';

export type HudState = 'idle' | 'listening' | 'thinking' | 'card' | 'repeat';

export interface HudMessage {
  type: 'hud';
  state: HudState;
  id?: string;
  partial?: string;
  question?: string;
  lead?: string;
  points?: string[];
  source?: string;
  confidence?: number;
}

const IDLE: HudMessage = {type: 'hud', state: 'idle'};

function hubUrl(): string {
  const fromQuery = new URLSearchParams(location.search).get('hub');
  return fromQuery ?? 'ws://127.0.0.1:8000/hud';
}

/** Connects to the hub, reconnecting after drops. Returns the latest HUD message and a sender. */
export function useHub() {
  const [message, setMessage] = useState<HudMessage>(IDLE);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    let retry: number | undefined;

    const connect = () => {
      const socket = new WebSocket(hubUrl());
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
