import { ListRestart, Trash2, User, Gift, Gem, PlayCircle, Clock, History, CheckCircle2 } from "lucide-react";
import { useState } from "react";

export function QueuePanel({ status, post }) {
  const [viewMode, setViewMode] = useState("queue"); // "queue" | "history"

  const items = status.current ? [status.current, ...status.queue] : status.queue;
  const historyItems = status.gift_history || [];
  const totalCount = status.queue_total ?? items.length;
  const pendingCount = status.queue_pending ?? status.queue.length;

  return (
    <section className="queue-panel">
      <div className="queue-title">
        <div className="queue-tab-group">
          <button
            className={`queue-tab-btn ${viewMode === "queue" ? "active" : ""}`}
            onClick={() => setViewMode("queue")}
          >
            <ListRestart size={15} />
            <strong>Hàng đợi</strong>
            <span className="queue-count-badge">{totalCount}</span>
          </button>
          <button
            className={`queue-tab-btn ${viewMode === "history" ? "active" : ""}`}
            onClick={() => setViewMode("history")}
          >
            <History size={15} />
            <strong>Log tặng quà</strong>
            <span className="queue-count-badge history-badge">{historyItems.length}</span>
          </button>
        </div>
        <div>
          {viewMode === "queue" ? (
            <button
              className="icon-button"
              onClick={() => post("/api/queue/clear")}
              title="Dừng action và xóa hàng đợi"
            >
              <Trash2 size={15} />
            </button>
          ) : (
            <button
              className="icon-button"
              onClick={() => post("/api/queue/clear-history")}
              title="Xóa nhật ký quà tặng"
            >
              <Trash2 size={15} />
            </button>
          )}
        </div>
      </div>

      {viewMode === "queue" ? (
        <div className="queue-list">
          {items.length ? (
            items.map((item, index) => {
              const isActive = index === 0 && status.current;
              const sender = item.sender || "Người xem";
              const giftName = item.gift || "Quà tặng";
              const count = item.count || 1;
              const diamonds = item.diamonds || 0;
              return (
                <div className={`queue-row ${isActive ? "active" : ""}`} key={`${giftName}-${item.file}-${index}`}>
                  <span className="queue-index">{String(index + 1).padStart(2, "0")}</span>
                  <div className="queue-row-content">
                    <div className="queue-row-header">
                      <span className="queue-sender" title="Người tặng">
                        <User size={13} /> <strong>{sender}</strong>
                      </span>
                      <span className="queue-gift-name">
                        <Gift size={13} /> {giftName} {count > 1 ? <b className="gift-count">x{count}</b> : null}
                      </span>
                      {diamonds > 0 && (
                        <span className="queue-diamonds" title="Diamond">
                          <Gem size={12} /> {diamonds}
                        </span>
                      )}
                    </div>
                    <div className="queue-row-sub">
                      <span className="queue-filename">{item.file}</span>
                      {item.timestamp && <span className="queue-time"><Clock size={11} /> {item.timestamp}</span>}
                    </div>
                  </div>
                  <div className="queue-row-tags">
                    {isActive ? (
                      <span className="status-pill active-pill"><PlayCircle size={12} /> ĐANG PHÁT</span>
                    ) : (
                      <span className="status-pill pending-pill">Chờ phát</span>
                    )}
                    <b className="priority-tag">P{item.priority ?? 1}</b>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="empty-queue">
              <p>Queue đang trống</p>
              {historyItems.length > 0 && (
                <button className="switch-history-btn" onClick={() => setViewMode("history")}>
                  <History size={13} /> Xem {historyItems.length} log tặng quà vừa nhận
                </button>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="queue-list history-list">
          {historyItems.length ? (
            historyItems.map((item, index) => {
              const sender = item.sender || "Người xem";
              const giftName = item.gift || "Quà tặng";
              const count = item.count || 1;
              const diamonds = item.diamonds || 0;
              const isCurrent = status.current && status.current.gift === item.gift && status.current.sender === item.sender;
              return (
                <div className={`queue-row history-row ${isCurrent ? "active" : ""}`} key={item.id || index}>
                  <span className="queue-index">{String(index + 1).padStart(2, "0")}</span>
                  <div className="queue-row-content">
                    <div className="queue-row-header">
                      <span className="queue-sender">
                        <User size={13} /> <strong>{sender}</strong>
                      </span>
                      <span className="queue-gift-name">
                        <Gift size={13} /> {giftName} {count > 1 ? <b className="gift-count">x{count}</b> : null}
                      </span>
                      {diamonds > 0 && (
                        <span className="queue-diamonds">
                          <Gem size={12} /> {diamonds}
                        </span>
                      )}
                    </div>
                    <div className="queue-row-sub">
                      <span className="queue-filename">{item.file}</span>
                      {item.timestamp && <span className="queue-time"><Clock size={11} /> {item.timestamp}</span>}
                    </div>
                  </div>
                  <div className="queue-row-tags">
                    {isCurrent ? (
                      <span className="status-pill active-pill"><PlayCircle size={12} /> ĐANG PHÁT</span>
                    ) : (
                      <span className="status-pill done-pill"><CheckCircle2 size={12} /> Đã nhận</span>
                    )}
                  </div>
                </div>
              );
            })
          ) : (
            <div className="empty-queue">Chưa có lịch sử quà tặng nào</div>
          )}
        </div>
      )}
    </section>
  );
}
