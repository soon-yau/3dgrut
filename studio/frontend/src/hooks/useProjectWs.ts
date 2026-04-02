import { useEffect, useRef, useState } from "react";

export type WsEvent =
  | { type: "log"; stage: string; backend: string | null; line: string }
  | { type: "status"; stage: string; status: string; backend: string | null }
  | { type: "metric"; iteration: number; [k: string]: unknown }
  | Record<string, unknown>;

function wsUrl(projectId: string) {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;
  return `${proto}//${host}/ws/${projectId}`;
}

export function useProjectWs(projectId: string | null) {
  const [lines, setLines] = useState<string[]>([]);
  const [lastStatus, setLastStatus] = useState<string>("");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!projectId) return;
    setLines([]);
    const ws = new WebSocket(wsUrl(projectId));
    wsRef.current = ws;
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as WsEvent;
        if (msg.type === "log" && "line" in msg) {
          setLines((L) => [...L.slice(-400), `[${msg.stage}] ${msg.line}`]);
        }
        if (msg.type === "status") {
          setLastStatus(`${msg.stage}: ${msg.status}`);
        }
      } catch {
        setLines((L) => [...L, ev.data]);
      }
    };
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [projectId]);

  return { lines, lastStatus };
}
