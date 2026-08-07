import { TerminalSquare, Gift } from "lucide-react";

export function LogsPanel({ logs }) {
  return (
    <section className="logs-panel">
      <div className="logs-title"><TerminalSquare size={15} /> System stream</div>
      <div className="logs-stream">
        {logs.length ? logs.slice(-7).map((item) => {
          const isGiftLog = item.message.includes("⚡ [TRIGGER:") || item.message.includes("🎁 [GIFT]") || item.message.includes("vừa tặng");
          return (
            <div className={`log-line ${item.level} ${isGiftLog ? "gift-log-line" : ""}`} key={item.id}>
              {isGiftLog && <Gift size={12} className="gift-log-icon" />}
              <span>{item.message}</span>
            </div>
          );
        }) : <div className="log-line muted">Backend đang khởi động…</div>}
      </div>
    </section>
  );
}
