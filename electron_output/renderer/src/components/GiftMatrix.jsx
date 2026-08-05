import { Plus, Save, TestTube2, Trash2 } from "lucide-react";

export function GiftMatrix({ mappings, setMappings, post, onNotice }) {
  const update = (index, key, value) => {
    setMappings((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item));
  };

  const save = async () => {
    const next = await post("/api/mappings", { items: mappings });
    setMappings(next);
    onNotice("Đã lưu Gift Mapping");
  };

  const add = () => setMappings((current) => [...current, { gift: "new_gift", action: "", priority: 1, sound: "" }]);
  const remove = (index) => setMappings((current) => current.filter((_, itemIndex) => itemIndex !== index));

  return (
    <section className="gift-panel">
      <div className="panel-heading compact">
        <div><span>TRIGGER MATRIX</span><h2>Quà và hành động</h2></div>
        <div className="heading-actions">
          <button className="icon-button" onClick={add} title="Thêm quà"><Plus size={17} /></button>
          <button className="icon-button accent" onClick={save} title="Lưu mapping"><Save size={17} /></button>
        </div>
      </div>
      <div className="gift-list">
        {mappings.map((item, index) => (
          <article className="gift-row" key={`${item.gift}-${index}`}>
            <div className="gift-topline">
              <input className="gift-name" value={item.gift} onChange={(event) => update(index, "gift", event.target.value)} aria-label="Tên quà" />
              <label className="priority-field">P<input type="number" min="1" max="9" value={item.priority} onChange={(event) => update(index, "priority", Number(event.target.value))} /></label>
              <button onClick={() => post("/api/queue/test", { gift: item.gift })} title="Test quà"><TestTube2 size={15} /></button>
              <button onClick={() => remove(index)} title="Xóa"><Trash2 size={15} /></button>
            </div>
            <input value={item.action} onChange={(event) => update(index, "action", event.target.value)} placeholder="Video, danh sách video hoặc action preset" aria-label="Action" />
            <div className="gift-detail">
              <span>{item.action_name || "Custom Video"}</span>
              <span>{item.videos?.length || 0} media</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
