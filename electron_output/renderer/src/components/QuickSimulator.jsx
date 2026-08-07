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
  const [gift, setGift] = useState("");
  const [sender, setSender] = useState("Người xem thử");
  const [count, setCount] = useState(1);
  const [diamonds, setDiamonds] = useState(0);

  const activeGifts = status.active_gifts || [];
  const activeGiftNames = new Set(activeGifts.map((item) => item.gift));
  const activeMappings = activeGifts.map((activeGift) => (
    (mappings || []).find((item) => item.gift === activeGift.gift) || {
      gift: activeGift.gift,
      action_name: activeGift.action_name,
      priority: activeGift.priority,
      videos: Array(activeGift.video_count).fill("video"),
      active: true,
    }
  ));
  const acceptingGifts = Boolean(status.running && (status.mock_mode || status.tiktok_connected));
  const simulatedGifts = Boolean(status.running && status.mock_mode);

  useEffect(() => {
    if (!activeGiftNames.has(gift)) setGift(activeMappings[0]?.gift || "");
  }, [gift, mappings, status.active_gifts]);

  const selected = mappings?.find((item) => item.gift === gift);

  const trigger = async () => {
    if (!gift) return onNotice("Chưa có quà để giả lập", "error");
    if (!activeGiftNames.has(gift)) return onNotice("Quà này chưa active hoặc đang thiếu video", "error");
    if (!status.running) return onNotice("Hãy bật nguồn giả lập trước", "error");
    const repeat = Math.max(1, Math.min(20, Number(count) || 1));
    await post("/api/queue/test-batch", { gift, count: repeat, sender, diamonds: Number(diamonds) || 0 });
    onNotice(`Đã kích hoạt ${gift} × ${repeat}`);
  };

  const copyGiftGuide = async () => {
    if (!activeGifts.length) return onNotice("Chưa có quà active để hướng dẫn", "error");
    const names = activeGifts.map((item) => GIFT_LABELS[item.gift] || `🎁 ${item.gift}`);
    const message = `Quà đang kích hoạt: ${names.join(", ")}. Hãy tặng một trong các quà trên để mở hành động!`;
    try {
      await copyText(message);
      onNotice("Đã sao chép danh sách quà đang active");
    } catch (error) {
      onNotice(`Không sao chép được: ${error.message}`, "error");
    }
  };

  return (
    <section className="quick-simulator dashboard-card">
      <div className="dashboard-card-title">
        <div><FlaskConical size={16} /><span>Giả lập nhanh</span></div>
        <small>{simulatedGifts ? `${activeGifts.length} quà trong giả lập` : acceptingGifts ? `${activeGifts.length} quà đang nhận` : `${activeGifts.length} quà đã cấu hình`}</small>
      </div>
      <div className={`active-gift-guide ${acceptingGifts ? "is-live" : ""}`}>
        <div className="active-gift-guide-title">
          <span><CheckCircle2 size={14} /> {simulatedGifts ? "QUÀ ACTIVE TRONG GIẢ LẬP" : acceptingGifts ? "QUÀ ĐANG NHẬN TRỰC TIẾP" : "QUÀ ĐÃ SẴN SÀNG"}</span>
          <button onClick={copyGiftGuide} disabled={!activeGifts.length} title="Sao chép câu hướng dẫn người xem"><Copy size={13} /> Sao chép</button>
        </div>
        <div className="active-gift-chips">
          {activeGifts.length ? activeGifts.map((item) => (
            <span className="active-gift-chip" key={item.gift} title={`${item.action_name} · ${item.video_count} video`}>
              {GIFT_LABELS[item.gift] || `🎁 ${item.gift}`} <b>{item.video_count} video</b>
            </span>
          )) : <em>Chưa có quà nào đủ video để kích hoạt.</em>}
        </div>
        {!acceptingGifts && activeGifts.length ? <p>Bật kết nối TikTok để bắt đầu nhận các quà này.</p> : null}
      </div>
      <label className="field">
        <span>Loại sự kiện</span>
        <select disabled><option>Quà tặng</option></select>
      </label>
      <label className="field">
        <span>Tên quà / hành động</span>
        <select value={gift} onChange={(event) => setGift(event.target.value)}>
          {!activeMappings.length ? <option value="">Chưa có quà active</option> : null}
          {activeMappings.map((item) => (
            <option key={item.gift} value={item.gift}>
              {GIFT_LABELS[item.gift] || `🎁 ${item.gift}`}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Tên người xem</span>
        <input value={sender} onChange={(event) => setSender(event.target.value)} />
      </label>
      <div className="simulator-number-grid">
        <label className="field"><span>Số lượng</span><input type="number" min="1" max="20" value={count} onChange={(event) => setCount(event.target.value)} /></label>
        <label className="field"><span>Diamond / giá trị</span><input type="number" min="0" value={diamonds} onChange={(event) => setDiamonds(event.target.value)} /></label>
      </div>
      <div className="simulator-media">
        <span title={selected?.action}>{selected?.videos?.length || 0} video</span>
        <span title={selected?.sound}>{selected?.sound ? "Có audio" : "Không audio"}</span>
        <span>P{selected?.priority || 1}</span>
      </div>
      <button className="simulate-button" disabled={!gift} onClick={trigger}><Play size={15} fill="currentColor" /> Phát thử trong preview</button>
    </section>
  );
}
