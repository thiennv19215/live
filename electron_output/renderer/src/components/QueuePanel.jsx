import { ListRestart, Trash2 } from "lucide-react";

export function QueuePanel({ status, post }) {
  const items = status.current ? [status.current, ...status.queue] : status.queue;
  return (
    <section className="queue-panel">
      <div className="queue-title">
        <div><ListRestart size={17} /><strong>Hàng đợi</strong><span>{status.queue.length}</span></div>
        <button className="icon-button" onClick={() => post("/api/queue/clear")} title="Xóa queue"><Trash2 size={15} /></button>
      </div>
      <div className="queue-list">
        {items.length ? items.map((item, index) => (
          <div className={`queue-row ${index === 0 && status.current ? "active" : ""}`} key={`${item.gift}-${item.file}-${index}`}>
            <span className="queue-index">{String(index + 1).padStart(2, "0")}</span>
            <div><strong>{item.gift}</strong><span>{item.file}</span></div>
            <b>P{item.priority}</b>
          </div>
        )) : <div className="empty-queue">Queue đang trống</div>}
      </div>
    </section>
  );
}
