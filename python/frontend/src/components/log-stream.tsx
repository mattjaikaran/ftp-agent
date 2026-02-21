import { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";
import { useLogStream } from "@/hooks/use-log-stream";
import { Wifi, WifiOff, Trash2 } from "lucide-react";

const LEVEL_COLORS: Record<string, string> = {
  debug: "text-gray-400",
  info: "text-blue-400",
  warning: "text-amber-400",
  error: "text-red-400",
  critical: "text-red-600 font-bold",
};

export function LogStream() {
  const { messages, connected, clear } = useLogStream();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div className="rounded-xl border border-gray-200 bg-gray-950 shadow-sm">
      <div className="flex items-center justify-between border-b border-gray-800 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-gray-200">Live Logs</h3>
          {connected ? (
            <Wifi className="h-3.5 w-3.5 text-green-400" />
          ) : (
            <WifiOff className="h-3.5 w-3.5 text-red-400" />
          )}
          <span className="text-xs text-gray-500">
            {connected ? "Connected" : "Disconnected"}
          </span>
        </div>
        <button
          onClick={clear}
          className="rounded p-1 text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300"
          title="Clear logs"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
      <div ref={scrollRef} className="h-72 overflow-y-auto p-3 font-mono text-xs">
        {messages.length === 0 ? (
          <div className="py-8 text-center text-gray-600">
            {connected ? "Waiting for logs..." : "Connecting..."}
          </div>
        ) : (
          messages.map((msg, i) => (
            <div key={i} className="leading-5">
              <span className="text-gray-600">
                {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : "—"}
              </span>{" "}
              <span className={cn(LEVEL_COLORS[msg.level] ?? "text-gray-400")}>
                [{msg.level?.toUpperCase()}]
              </span>{" "}
              <span className="text-gray-300">{msg.event}</span>
              {Object.entries(msg)
                .filter(([k]) => !["timestamp", "level", "event"].includes(k))
                .map(([k, v]) => (
                  <span key={k} className="ml-2 text-gray-500">
                    {k}=
                    <span className="text-gray-400">{String(v)}</span>
                  </span>
                ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
