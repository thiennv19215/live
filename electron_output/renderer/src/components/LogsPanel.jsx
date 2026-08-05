import { TerminalSquare } from "lucide-react";

export function LogsPanel({ logs }) {
  return (
    <section className="logs-panel">
      <div className="logs-title"><TerminalSquare size={15} /> System stream</div>
      <div className="logs-stream">
        {logs.length ? logs.slice(-7).map((item) => (
          <div className={`log-line ${item.level}`} key={item.id}>{item.message}</div>
        )) : <div className="log-line muted">Backend đang khởi động…</div>}
      </div>
    </section>
  );
}
