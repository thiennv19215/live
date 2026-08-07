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

  const trigger = async () => {
    if (!triggerKey) return onNotice("Chưa có luật sự kiện để giả lập", "error");
    if (!activeKeys.has(triggerKey)) return onNotice("Luật này chưa active hoặc đang thiếu video", "error");
    if (!status.running) return onNotice("Hãy bật nguồn giả lập trước", "error");
    await post("/api/triggers/test", { trigger_key: triggerKey, sender });
    onNotice(`Đã kích hoạt: ${instructionLabel(selectedTrigger)}`);
  };

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
      <div className={`active-gift-guide ${acceptingEvents ? "is-live" : ""}`}>
        <div className="active-gift-guide-title">
          <span><CheckCircle2 size={14} /> {simulatedEvents ? "SỰ KIỆN ACTIVE TRONG GIẢ LẬP" : acceptingEvents ? "SỰ KIỆN ĐANG NHẬN TRỰC TIẾP" : "SỰ KIỆN ĐÃ SẴN SÀNG"}</span>
          <button onClick={copyEventGuide} disabled={!activeTriggers.length} title="Sao chép câu hướng dẫn người xem"><Copy size={13} /> Sao chép</button>
        </div>
        <div className="active-gift-chips">
          {activeTriggers.length ? activeTriggers.map((item) => (
            <span className="active-gift-chip" key={item.trigger_key} title={`${item.action_name} · ${item.video_count} video`}>
              {instructionLabel(item)} <b>{item.video_count} video</b>
            </span>
          )) : <em>Chưa có luật sự kiện nào đủ video để kích hoạt.</em>}
        </div>
        {!acceptingEvents && activeTriggers.length ? <p>Bật kết nối TikTok để bắt đầu nhận các sự kiện này.</p> : null}
      </div>
      <label className="field">
        <span>Luật sự kiện / hành động</span>
        <select value={triggerKey} onChange={(event) => setTriggerKey(event.target.value)}>
          {!activeTriggers.length ? <option value="">Chưa có sự kiện active</option> : null}
          {activeTriggers.map((item) => (
            <option key={item.trigger_key} value={item.trigger_key}>
              {instructionLabel(item)} → {item.action_name}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Tên người xem</span>
        <input value={sender} onChange={(event) => setSender(event.target.value)} />
      </label>
      <div className="simulator-media">
        <span>{selectedTrigger?.event_label || "Chưa chọn sự kiện"}</span>
        <span title={selected?.action}>{selectedTrigger?.video_count || 0} video</span>
        <span title={selected?.sound}>{selected?.sound ? "Có audio" : "Không audio"}</span>
        <span>P{selected?.priority || 1}</span>
      </div>
      <button className="simulate-button" disabled={!triggerKey} onClick={trigger}><Play size={15} fill="currentColor" /> Phát thử sự kiện trong preview</button>
    </section>
  );
}
