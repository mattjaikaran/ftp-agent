import { useEffect, useRef, useState, useCallback } from "react";
import type { LogMessage } from "@/lib/types";

const MAX_MESSAGES = 500;

export function useLogStream() {
  const [messages, setMessages] = useState<LogMessage[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/logs`);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      // Reconnect after 3 seconds
      setTimeout(connect, 3000);
    };
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as LogMessage;
        setMessages((prev) => [...prev.slice(-(MAX_MESSAGES - 1)), msg]);
      } catch {
        // Ignore non-JSON messages
      }
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);

  const clear = useCallback(() => setMessages([]), []);

  return { messages, connected, clear };
}
