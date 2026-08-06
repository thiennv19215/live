import { FlaskConical, Play } from "lucide-react";
import { useEffect, useState } from "react";

export function QuickSimulator({ mappings, status, post, onNotice }) {
  const [gift, setGift] = useState("");
  const [sender, setSender] = useState("Người xem thử");
  const [count, setCount] = useState(1);
  const [diamonds, setDiamonds] = useState(0);

  useEffect(() => {
    if (!gift && mappings?.length) setGift(mappings[0].gift);
  }, [gift, mappings]);

  const selected = mappings?.find((item) => item.gift === gift);

  const trigger = async () => {
    if (!gift) return onNotice("Chưa có quà để giả lập", "error");
    if (!status.running) return onNotice("Hãy bật nguồn giả lập trước", "error");
    const repeat = Math.max(1, Math.min(20, Number(count) || 1));
    await post("/api/queue/test-batch", { gift, count: repeat, sender, diamonds: Number(diamonds) || 0 });
    onNotice(`Đã kích hoạt ${gift} × ${repeat}`);
  };

  return (
    <section className="quick-simulator dashboard-card">
      <div className="dashboard-card-title">
        <div><FlaskConical size={16} /><span>Giả lập nhanh</span></div>
        <small>{status.running ? "Sẵn sàng" : "Chưa chạy"}</small>
      </div>
      <label className="field">
        <span>Loại sự kiện</span>
        <select disabled><option>Quà tặng</option></select>
      </label>
      <label className="field">
        <span>Tên quà / hành động</span>
        <select value={gift} onChange={(event) => setGift(event.target.value)}>
          {(mappings || []).map((item) => <option key={item.gift} value={item.gift}>{item.gift}</option>)}
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
      <button className="simulate-button" onClick={trigger}><Play size={15} fill="currentColor" /> Phát thử trong preview</button>
    </section>
  );
}
