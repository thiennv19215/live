import { FolderOpen, Music2, Play, Plus, Save, Trash2, Video } from "lucide-react";

const fileName = (path = "") => path.split(/[\\/]/).at(-1) || "Chưa gán";

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
  const persist = async (items, message) => {
    const saved = await post("/api/mappings", { items });
    setMappings(saved);
    onNotice(message);
  };

  const pickVideo = async (index) => {
    const paths = await window.desktop?.pickMedia?.({ title: `Gán video cho ${mappings[index].gift}`, multiple: true });
    if (!paths?.length) return;
    const items = mappings.map((item, itemIndex) => itemIndex === index ? { ...item, action: paths.join(", ") } : item);
    await persist(items, `Đã gán ${paths.length} video cho ${mappings[index].gift}`);
  };

  const pickAudio = async (index) => {
    const path = await window.desktop?.pickMedia?.({ title: `Gán audio cho ${mappings[index].gift}`, kind: "audio" });
    if (!path) return;
    const items = mappings.map((item, itemIndex) => itemIndex === index ? { ...item, sound: path } : item);
    await persist(items, `Đã gán audio cho ${mappings[index].gift}`);
  };

  const remove = async (index) => {
    const items = mappings.filter((_, itemIndex) => itemIndex !== index);
    await persist(items, "Đã xóa mapping quà");
  };

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
            <div className="gift-topline assignment-topline">
              <input className="gift-name" value={item.gift} onChange={(event) => update(index, "gift", event.target.value)} aria-label="Tên quà" />
              <label className="priority-field">P<input type="number" min="1" max="9" value={item.priority} onChange={(event) => update(index, "priority", Number(event.target.value))} /></label>
              <button onClick={() => remove(index)} title="Xóa"><Trash2 size={15} /></button>
            </div>
            <div className="assignment-summary">
              <div><Video size={15} /><span><small>VIDEO HÀNH ĐỘNG</small><strong title={item.action}>{item.videos?.length > 1 ? `${item.videos.length} video đã gán` : fileName(item.videos?.[0] || item.action)}</strong></span></div>
              <div><Music2 size={15} /><span><small>AUDIO</small><strong title={item.sound}>{fileName(item.sound)}</strong></span></div>
            </div>
            <div className="assignment-actions">
              <button onClick={() => pickVideo(index)}><FolderOpen size={14} /> Gán video</button>
              <button onClick={() => pickAudio(index)}><Music2 size={14} /> Gán audio</button>
              <button className="test" onClick={() => post("/api/queue/test", { gift: item.gift })}><Play size={14} fill="currentColor" /> Phát thử</button>
            </div>
            <div className="gift-detail"><span>{item.action_name || "Custom Video"}</span><span>P{item.priority}</span></div>
          </article>
        ))}
      </div>
    </section>
  );
}
