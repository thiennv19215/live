import { FolderOpen, Music2, Play, Plus, Save, Trash2, Video } from "lucide-react";

const fileName = (path = "") => path.split(/[\\/]/).at(-1) || "Chưa gán";

const POPULAR_GIFTS = [
  { id: "rose", name: "🌹 Rose (Hoa hồng)" },
  { id: "tiktok", name: "🎵 TikTok (Logo)" },
  { id: "ice cream", name: "🍦 Ice Cream (Kem)" },
  { id: "finger heart", name: "🫰 Finger Heart (Bắn tim)" },
  { id: "doughnut", name: "🍩 Doughnut (Donut)" },
  { id: "perfume", name: "🧴 Perfume (Nước hoa)" },
  { id: "paper crane", name: "📜 Paper Crane (Hạc giấy)" },
  { id: "sunglasses", name: "🕶️ Sunglasses (Kính mát)" },
  { id: "hand heart", name: "🫶 Hand Heart (Mở tim)" },
  { id: "cap", name: "🧢 Cap (Nón)" },
  { id: "lion", name: "🦁 Lion (Sư tử)" },
  { id: "sports car", name: "🏎️ Sports Car (Siêu xe)" },
  { id: "spaceship", name: "🚀 Spaceship (Tàu vũ trụ)" },
  { id: "dragon", name: "🐲 Dragon (Rồng)" },
  { id: "universe", name: "🌌 TikTok Universe (Vũ trụ)" },
];

export function GiftMatrix({ mappings, setMappings, actions, setActions, post, reloadConfig, onNotice }) {
  const updateMapping = (index, key, value) => {
    setMappings((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item));
  };

  const chooseAction = (index, actionId) => {
    const preset = actions.find((item) => item.id === actionId);
    setMappings((current) => current.map((item, itemIndex) => itemIndex === index ? {
      ...item,
      action: actionId,
      action_id: actionId,
      action_name: preset?.name || actionId,
      videos: preset?.videos || [],
      resolved_sound: preset?.sound || "",
      sound: "",
    } : item));
  };

  const saveMappings = async () => {
    const next = await post("/api/mappings", { items: mappings });
    setMappings(next);
    await reloadConfig?.();
    onNotice("Đã lưu luật quà → hành động");
  };

  const addMapping = () => {
    const first = actions[0];
    setMappings((current) => [...current, {
      gift: "rose",
      action: first?.id || "",
      action_id: first?.id || "",
      action_name: first?.name || "",
      videos: first?.videos || [],
      priority: 1,
      sound: "",
    }]);
  };

  const removeMapping = async (index) => {
    const items = mappings.filter((_, itemIndex) => itemIndex !== index);
    const saved = await post("/api/mappings", { items });
    setMappings(saved);
    onNotice("Đã xóa luật quà");
  };

  const updateAction = (index, key, value) => {
    setActions((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item));
  };

  const persistActions = async (items, message) => {
    const saved = await post("/api/actions", { items });
    setActions(saved);
    await reloadConfig?.();
    onNotice(message);
  };

  const saveActions = () => persistActions(actions, "Đã lưu kho hành động");

  const addAction = () => {
    const used = new Set(actions.map((item) => item.id));
    let number = actions.length + 1;
    while (used.has(`action_${number}`)) number += 1;
    setActions((current) => [...current, { id: `action_${number}`, name: "Hành động mới", videos: [], sound: "" }]);
  };

  const pickVideo = async (index) => {
    const paths = await window.desktop?.pickMedia?.({ title: `Gán video cho ${actions[index].name}`, multiple: true, copyToLibrary: true });
    if (!paths?.length) return;
    const items = actions.map((item, itemIndex) => itemIndex === index ? { ...item, videos: paths } : item);
    await persistActions(items, `Đã gán ${paths.length} video cho hành động`);
  };

  const pickAudio = async (index) => {
    const path = await window.desktop?.pickMedia?.({ title: `Gán audio cho ${actions[index].name}`, kind: "audio", copyToLibrary: true });
    if (!path) return;
    const items = actions.map((item, itemIndex) => itemIndex === index ? { ...item, sound: path } : item);
    await persistActions(items, "Đã gán audio cho hành động");
  };

  const removeAction = async (index) => {
    const action = actions[index];
    if (mappings.some((item) => (item.action_id || item.action) === action.id)) {
      onNotice("Hành động đang được một quà sử dụng", "error");
      return;
    }
    await persistActions(actions.filter((_, itemIndex) => itemIndex !== index), "Đã xóa hành động");
  };

  return (
    <section className="gift-panel">
      <div className="panel-heading compact">
        <div><span>TRIGGER RULES</span><h2>Quà → hành động</h2></div>
        <div className="heading-actions">
          <button className="icon-button" onClick={addMapping} title="Thêm luật quà"><Plus size={17} /></button>
          <button className="icon-button accent" onClick={saveMappings} title="Lưu luật"><Save size={17} /></button>
        </div>
      </div>

      <div className="gift-list mapping-list">
        {mappings.map((item, index) => {
          const selectedId = item.action_id || item.action;
          const isLegacy = selectedId && !actions.some((action) => action.id === selectedId);
          const isKnownPreset = POPULAR_GIFTS.some((g) => g.id === item.gift);
          return (
            <article className="gift-row" key={`${item.gift}-${index}`}>
              <div className="gift-topline assignment-topline rule-topline">
                <div className="gift-picker-box">
                  <select
                    className="gift-preset-select"
                    value={isKnownPreset ? item.gift : "custom"}
                    onChange={(e) => {
                      if (e.target.value !== "custom") {
                        updateMapping(index, "gift", e.target.value);
                      }
                    }}
                    title="Chọn quà có sẵn"
                  >
                    <option value="" disabled>-- Chọn quà TikTok --</option>
                    {POPULAR_GIFTS.map((g) => (
                      <option value={g.id} key={g.id}>{g.name}</option>
                    ))}
                    <option value="custom">✏️ Nhập quà khác...</option>
                  </select>
                  <input
                    className="gift-name"
                    value={item.gift}
                    placeholder="Mã quà..."
                    onChange={(event) => updateMapping(index, "gift", event.target.value)}
                    aria-label="Tên quà"
                    title="Tên mã quà TikTok (viết thường)"
                  />
                </div>
                <select value={selectedId} onChange={(event) => chooseAction(index, event.target.value)} aria-label="Hành động">
                  <option value="">Chọn hành động…</option>
                  {isLegacy ? <option value={selectedId}>Cấu hình cũ · sẽ tự chuyển đổi</option> : null}
                  {actions.map((action) => <option value={action.id} key={action.id}>{action.name}</option>)}
                </select>
                <button onClick={() => removeMapping(index)} title="Xóa"><Trash2 size={15} /></button>
              </div>
              <div className="gift-detail"><span>{item.action_name || selectedId || "Chưa chọn"}</span><span>FIFO</span></div>
              <div className="assignment-actions rule-actions">
                <button className="test" disabled={!selectedId} onClick={() => post("/api/queue/test", { gift: item.gift })}><Play size={14} fill="currentColor" /> Phát thử</button>
              </div>
            </article>
          );
        })}
      </div>

      <div className="panel-heading compact action-library-heading">
        <div><span>ACTION LIBRARY</span><h2>Kho hành động dùng chung</h2></div>
        <div className="heading-actions">
          <button className="icon-button" onClick={addAction} title="Thêm hành động"><Plus size={17} /></button>
          <button className="icon-button accent" onClick={saveActions} title="Lưu hành động"><Save size={17} /></button>
        </div>
      </div>

      <div className="gift-list action-list">
        {actions.map((action, index) => (
          <article className="gift-row action-row" key={action.id}>
            <div className="gift-topline assignment-topline action-topline">
              <input value={action.name} onChange={(event) => updateAction(index, "name", event.target.value)} aria-label="Tên hành động" />
              <code title="Mã ổn định dùng trong mapping">{action.id}</code>
              <button onClick={() => removeAction(index)} title="Xóa"><Trash2 size={15} /></button>
            </div>
            <div className="assignment-summary">
              <div><Video size={15} /><span><small>VIDEO</small><strong>{action.videos?.length > 1 ? `${action.videos.length} video` : fileName(action.videos?.[0])}</strong></span></div>
              <div><Music2 size={15} /><span><small>AUDIO</small><strong>{fileName(action.sound)}</strong></span></div>
            </div>
            <div className="assignment-actions action-buttons">
              <button onClick={() => pickVideo(index)}><FolderOpen size={14} /> Gán video</button>
              <button onClick={() => pickAudio(index)}><Music2 size={14} /> Gán audio</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
