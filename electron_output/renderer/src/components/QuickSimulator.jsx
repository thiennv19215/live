import { CheckCircle2, Copy, FlaskConical, Play } from "lucide-react";
import { useEffect, useState } from "react";

const GIFT_LABELS = {
  rose: "🌹 Rose (Hoa hồng)",
  tiktok: "🎵 TikTok (Logo)",
  "ice cream": "🍦 Ice Cream (Kem)",
  "finger heart": "🫰 Finger Heart (Bắn tim)",
  doughnut: "🍩 Doughnut (Donut)",
  perfume: "🧴 Perfume (Nước hoa)",
  "paper crane": "📜 Paper Crane (Hạc giấy)",
  sunglasses: "🕶️ Sunglasses (Kính mát)",
  "hand heart": "🫶 Hand Heart (Mở tim)",
  cap: "🧢 Cap (Nón)",
  lion: "🦁 Lion (Sư tử)",
  "sports car": "🏎️ Sports Car (Siêu xe)",
  spaceship: "🚀 Spaceship (Tàu vũ trụ)",
  dragon: "🐲 Dragon (Rồng)",
  universe: "🌌 TikTok Universe (Vũ trụ)",
};

const GIFT_ICONS = {
  rose: "🌹",
  tiktok: "🎵",
  "ice cream": "🍦",
  "finger heart": "🫰",
  doughnut: "🍩",
  perfume: "🧴",
  "paper crane": "📜",
  sunglasses: "🕶️",
  "hand heart": "🫶",
  cap: "🧢",
  lion: "🦁",
  "sports car": "🏎️",
  spaceship: "🚀",
  dragon: "🐲",
  universe: "🌌",
};

const EVENT_ICONS = {
  comment: "💬",
  follow: "➕",
  share: "↗️",
  like: "❤️",
  join: "👋",
  subscribe: "⭐",
};

async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch {
    // Fall through to the legacy copy path used by some Electron/file origins.
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("Trình duyệt không cấp quyền clipboard");
}

export function QuickSimulator({ mappings, status, post, onNotice }) {
  const [triggerKey, setTriggerKey] = useState("");
  const [sender, setSender] = useState("Người xem thử");

  const activeTriggers = status.active_triggers || (status.active_gifts || []).map((item) => ({
    ...item,
    trigger_key: item.gift,
    event_type: "gift",
    condition: item.gift,
    event_label: `Quà: ${item.gift}`,
  }));
  const activeKeys = new Set(activeTriggers.map((item) => item.trigger_key));
  const acceptingEvents = Boolean(status.running && (status.mock_mode || status.tiktok_connected));
  const simulatedEvents = Boolean(status.running && status.mock_mode);

  const instructionLabel = (item) => {
    if (item.event_type === "gift") return GIFT_LABELS[item.condition] || `🎁 Tặng ${item.condition}`;
    if (item.event_type === "comment") return `💬 Bình luận “${item.condition}”`;
    if (item.event_type === "follow") return "➕ Theo dõi kênh";
    if (item.event_type === "share") return "↗ Chia sẻ live";
    if (item.event_type === "like") return `❤️ Thả ít nhất ${item.condition || 1} like`;
    if (item.event_type === "join") return "👋 Vào phòng live";
    if (item.event_type === "subscribe") return "⭐ Đăng ký LIVE";
    return item.event_label || item.trigger_key;
  };

  useEffect(() => {
    if (!activeKeys.has(triggerKey)) setTriggerKey(activeTriggers[0]?.trigger_key || "");
  }, [triggerKey, mappings, status.active_triggers, status.active_gifts]);

  const selected = mappings?.find((item) => (item.trigger_key || item.gift) === triggerKey);
  const selectedTrigger = activeTriggers.find((item) => item.trigger_key === triggerKey);

  const trigger = async (target = selectedTrigger) => {
    const nextKey = target?.trigger_key || triggerKey;
    if (!nextKey) return onNotice("Chưa có luật sự kiện để giả lập", "error");
    setTriggerKey(nextKey);
    if (!activeKeys.has(nextKey)) return onNotice("Luật này chưa active hoặc đang thiếu video", "error");
    if (!status.running) return onNotice("Hãy bật nguồn giả lập trước", "error");
    await post("/api/triggers/test", { trigger_key: nextKey, sender });
    onNotice(`Đã kích hoạt: ${instructionLabel(target || selectedTrigger)}`);
  };

  const eventIcon = (item) => item?.event_type === "gift"
    ? (GIFT_ICONS[item.condition] || "🎁")
    : (EVENT_ICONS[item?.event_type] || "⚡");

  const copyEventGuide = async () => {
    if (!activeTriggers.length) return onNotice("Chưa có sự kiện active để hướng dẫn", "error");
    const message = `Tương tác đang kích hoạt: ${activeTriggers.map(instructionLabel).join(", ")}. Hãy thực hiện một trong các tương tác trên để mở hành động!`;
    try {
      await copyText(message);
      onNotice("Đã sao chép hướng dẫn tương tác đang active");
    } catch (error) {
      onNotice(`Không sao chép được: ${error.message}`, "error");
    }
  };

  return (
    <section className="quick-simulator dashboard-card">
      <div className="dashboard-card-title">
        <div><FlaskConical size={16} /><span>Giả lập nhanh</span></div>
        <small>{simulatedEvents ? `${activeTriggers.length} luật trong giả lập` : acceptingEvents ? `${activeTriggers.length} luật đang nhận` : `${activeTriggers.length} luật đã cấu hình`}</small>
      </div>
      <div className={`event-reactions ${acceptingEvents ? "is-live" : ""}`}>
        <div className="event-reactions-heading">
          <div>
            <span>EVENT REACTIONS</span>
            <strong>{activeTriggers.length} sự kiện</strong>
          </div>
          <button onClick={copyEventGuide} disabled={!activeTriggers.length} title="Sao chép câu hướng dẫn người xem"><Copy size={13} /> Sao chép</button>
        </div>
        <p>Bấm vào một sự kiện để xem thử hành động</p>
        <div className="event-reaction-list" role="list" aria-label="Danh sách sự kiện để test">
          {activeTriggers.length ? activeTriggers.map((item) => (
            <button
              type="button"
              role="listitem"
              className={`event-reaction-row event-${item.event_type} ${triggerKey === item.trigger_key ? "selected" : ""}`}
              key={item.trigger_key}
              onClick={() => trigger(item)}
              title={`Test ${instructionLabel(item)} → ${item.action_name}`}
            >
              <span className="event-reaction-icon" aria-hidden="true">{eventIcon(item)}</span>
              <span className="event-reaction-copy">
                <strong>{instructionLabel(item)}</strong>
                <small>{item.action_name}</small>
              </span>
              <span className="event-reaction-meta">
                <b>{item.video_count}</b>
                <small>video</small>
                <Play size={13} fill="currentColor" />
              </span>
            </button>
          )) : <div className="event-reactions-empty">Chưa có luật sự kiện nào đủ video để kích hoạt.</div>}
        </div>
        <div className="event-reactions-status">
          <CheckCircle2 size={13} />
          {simulatedEvents ? "Đang chạy chế độ giả lập" : acceptingEvents ? "Đang nhận sự kiện trực tiếp" : "Sẵn sàng — hãy bật TikTok hoặc giả lập"}
        </div>
      </div>
      <label className="field">
        <span>Tên người xem</span>
        <input value={sender} onChange={(event) => setSender(event.target.value)} />
      </label>
      <div className="simulator-media">
        <span>{selectedTrigger?.event_label || "Chưa chọn sự kiện"}</span>
        <span title={selected?.action}>{selectedTrigger?.video_count || 0} video</span>
        <span title={selected?.sound}>{selected?.sound ? "Có audio" : "Không audio"}</span>
      </div>
      <button className="simulate-button" disabled={!triggerKey} onClick={() => trigger()}><Play size={15} fill="currentColor" /> Phát lại sự kiện đã chọn</button>
    </section>
  );
}
