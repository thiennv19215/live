import { FolderOpen, Music2, Play, Plus, Save, Trash2, Video, X, Sparkles, ArrowUp, ArrowDown, ListOrdered } from "lucide-react";

const fileName = (path = "") => path.split(/[\\/]/).at(-1) || "Chưa gán";

const naturalSort = (a, b) => {
  const nameA = fileName(a);
  const nameB = fileName(b);
  return nameA.localeCompare(nameB, undefined, { numeric: true, sensitivity: "base" });
};

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
    try {
      const next = await post("/api/mappings", { items: mappings });
      setMappings(next);
      await reloadConfig?.();
      onNotice("Đã lưu luật quà → hành động");
    } catch (err) {
      onNotice(`Lỗi lưu luật quà: ${err.message}`, "error");
    }
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
    try {
      const items = mappings.filter((_, itemIndex) => itemIndex !== index);
      const saved = await post("/api/mappings", { items });
      setMappings(saved);
      onNotice("Đã xóa luật quà");
    } catch (err) {
      onNotice(`Lỗi xóa luật quà: ${err.message}`, "error");
    }
  };

  const updateAction = (index, key, value) => {
    setActions((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item));
  };

  const persistActions = async (items, message) => {
    try {
      const saved = await post("/api/actions", { items });
      setActions(saved);
      await reloadConfig?.();
      onNotice(message);
    } catch (err) {
      onNotice(`Lỗi lưu kho hành động: ${err.message}`, "error");
    }
  };

  const saveActions = () => persistActions(actions, "Đã lưu kho hành động");

  const addAction = () => {
    const used = new Set(actions.map((item) => item.id));
    let number = actions.length + 1;
    while (used.has(`action_${number}`)) number += 1;
    const newId = `action_${number}`;
    setActions((current) => [...current, { id: newId, name: `Hành động ${number}`, videos: [], sound: "" }]);
  };

  const pickVideo = async (index) => {
    const paths = await window.desktop?.pickMedia?.({ title: `Gán video cho ${actions[index].name}`, multiple: true, copyToLibrary: true });
    if (!paths?.length) return;
    const existing = actions[index].videos || [];
    const merged = Array.from(new Set([...existing, ...paths])).sort(naturalSort);
    const items = actions.map((item, itemIndex) => itemIndex === index ? { ...item, videos: merged } : item);
    await persistActions(items, `Đã gán video mới cho ${actions[index].name}`);
  };

  const pickFolder = async (index) => {
    const paths = await window.desktop?.pickFolder?.({ title: `Chọn thư mục video cho ${actions[index].name}`, copyToLibrary: true });
    if (!paths?.length) return;
    const existing = actions[index].videos || [];
    const merged = Array.from(new Set([...existing, ...paths])).sort(naturalSort);
    const items = actions.map((item, itemIndex) => itemIndex === index ? { ...item, videos: merged } : item);
    await persistActions(items, `Đã thêm ${paths.length} video từ thư mục cho ${actions[index].name}`);
  };

  const removeVideoFromAction = async (actionIndex, videoIndex) => {
    const targetAction = actions[actionIndex];
    const newVideos = (targetAction.videos || []).filter((_, vIdx) => vIdx !== videoIndex);
    const newActions = actions.map((item, idx) => idx === actionIndex ? { ...item, videos: newVideos } : item);
    await persistActions(newActions, "Đã gỡ video khỏi hành động");
  };

  const moveVideo = async (actionIndex, fromIdx, toIdx) => {
    const targetAction = actions[actionIndex];
    const videos = [...(targetAction.videos || [])];
    if (toIdx < 0 || toIdx >= videos.length) return;
    const temp = videos[fromIdx];
    videos[fromIdx] = videos[toIdx];
    videos[toIdx] = temp;
    const newActions = actions.map((item, idx) => idx === actionIndex ? { ...item, videos } : item);
    await persistActions(newActions, "Đã đổi thứ tự video");
  };

  const sortActionVideos = async (actionIndex) => {
    const targetAction = actions[actionIndex];
    const sorted = [...(targetAction.videos || [])].sort(naturalSort);
    const newActions = actions.map((item, idx) => idx === actionIndex ? { ...item, videos: sorted } : item);
    await persistActions(newActions, "Đã sắp xếp danh sách video theo 1-2-3");
  };

  const pickAudio = async (index) => {
    const path = await window.desktop?.pickMedia?.({ title: `Gán audio cho ${actions[index].name}`, kind: "audio", copyToLibrary: true });
    if (!path) return;
    const items = actions.map((item, itemIndex) => itemIndex === index ? { ...item, sound: path } : item);
    await persistActions(items, "Đã gán audio cho hành động");
  };

  const removeAudioFromAction = async (actionIndex) => {
    const newActions = actions.map((item, idx) => idx === actionIndex ? { ...item, sound: "" } : item);
    await persistActions(newActions, "Đã gỡ audio khỏi hành động");
  };

  const removeAction = async (index) => {
    const targetAction = actions[index];
    const newActions = actions.filter((_, itemIndex) => itemIndex !== index);

    // Automatically unbind or update any gift rules using this deleted action
    const affectedMappings = mappings.map((item) => {
      const currentActionId = item.action_id || item.action;
      if (currentActionId === targetAction.id) {
        const fallback = newActions[0];
        return {
          ...item,
          action: fallback?.id || "",
          action_id: fallback?.id || "",
          action_name: fallback?.name || "",
        };
      }
      return item;
    });

    try {
      await post("/api/actions", { items: newActions });
      const savedMappings = await post("/api/mappings", { items: affectedMappings });
      setActions(newActions);
      setMappings(savedMappings);
      await reloadConfig?.();
      onNotice(`Đã xóa hành động '${targetAction.name}'`);
    } catch (err) {
      onNotice(`Lỗi xóa hành động: ${err.message}`, "error");
    }
  };

  return (
    <section className="gift-panel">
      <div className="panel-heading compact">
        <div><span>TRIGGER RULES</span><h2>Quà → hành động</h2></div>
        <div className="heading-actions">
          <button className="icon-button" onClick={addMapping} title="Thêm luật quà mới"><Plus size={17} /></button>
          <button className="icon-button accent" onClick={saveMappings} title="Lưu các luật quà"><Save size={17} /></button>
        </div>
      </div>

      <div className="gift-list mapping-list">
        {mappings.map((item, index) => {
          const selectedId = item.action_id || item.action;
          const isLegacy = selectedId && !actions.some((action) => action.id === selectedId);
          const isKnownPreset = POPULAR_GIFTS.some((g) => g.id === item.gift);
          const linkedAction = actions.find((a) => a.id === selectedId);
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

                <div className="action-select-box">
                  <select value={selectedId} onChange={(event) => chooseAction(index, event.target.value)} aria-label="Hành động">
                    <option value="">Chọn hành động…</option>
                    {isLegacy ? <option value={selectedId}>Cấu hình cũ · {selectedId}</option> : null}
                    {actions.map((action) => (
                      <option value={action.id} key={action.id}>
                        ⚡ {action.name} ({action.videos?.length || 0} video)
                      </option>
                    ))}
                  </select>
                </div>

                <div className="priority-select-box" title="Độ ưu tiên hàng đợi">
                  <small className="priority-label">Ưu tiên:</small>
                  <select
                    value={item.priority || 1}
                    onChange={(e) => updateMapping(index, "priority", Number(e.target.value))}
                  >
                    <option value={1}>P1 - Bình thường</option>
                    <option value={2}>P2 - Trung bình</option>
                    <option value={3}>P3 - Cao</option>
                    <option value={4}>P4 - Rất cao</option>
                    <option value={5}>P5 - Khẩn cấp (Quà to)</option>
                  </select>
                </div>

                <button onClick={() => removeMapping(index)} title="Xóa luật"><Trash2 size={15} /></button>
              </div>

              <div className="gift-detail">
                <span>Hành động: <strong>{linkedAction?.name || item.action_name || selectedId || "Chưa chọn"}</strong></span>
                <span>Video: <strong>{linkedAction?.videos?.length ? `${linkedAction.videos.length} file` : "Chưa có"}</strong></span>
              </div>

              <div className="assignment-actions rule-actions">
                <button className="test" disabled={!selectedId} onClick={() => post("/api/queue/test", { gift: item.gift })}>
                  <Play size={14} fill="currentColor" /> Phát thử
                </button>
              </div>
            </article>
          );
        })}
      </div>

      <div className="panel-heading compact action-library-heading">
        <div><span>ACTION LIBRARY</span><h2>Kho hành động dùng chung</h2></div>
        <div className="heading-actions">
          <button className="icon-button" onClick={addAction} title="Thêm hành động mới"><Plus size={17} /></button>
          <button className="icon-button accent" onClick={saveActions} title="Lưu kho hành động"><Save size={17} /></button>
        </div>
      </div>

      <div className="gift-list action-list">
        {actions.map((action, index) => (
          <article className="gift-row action-row" key={action.id || index}>
            <div className="gift-topline assignment-topline action-topline">
              <input
                value={action.name}
                onChange={(event) => updateAction(index, "name", event.target.value)}
                aria-label="Tên hành động"
                placeholder="Tên hành động..."
              />
              <code title="Mã ID hành động">{action.id}</code>
              <button onClick={() => removeAction(index)} title="Xóa hành động này"><Trash2 size={15} /></button>
            </div>

            <div className="action-details-grid">
              {/* Video List Section */}
              <div className="action-media-section">
                <div className="action-section-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <Video size={14} />
                    <span>DANH SÁCH VIDEO ({action.videos?.length || 0})</span>
                  </div>
                  {action.videos?.length > 1 ? (
                    <button
                      className="icon-button-small"
                      onClick={() => sortActionVideos(index)}
                      title="Tự động sắp xếp video theo thứ tự tên (1➔2➔3)"
                      style={{ fontSize: "11px", padding: "2px 6px", display: "flex", alignItems: "center", gap: "4px" }}
                    >
                      <ListOrdered size={12} /> Sắp xếp 1-2-3
                    </button>
                  ) : null}
                </div>

                {action.videos?.length ? (
                  <div style={{ fontSize: "11px", color: "rgba(255,255,255,0.45)", margin: "2px 0 6px 0" }}>
                    ℹ️ Phát lần lượt: Video 1 ➔ Video 2 ➔ Video 3...
                  </div>
                ) : null}

                <div className="action-file-list">
                  {action.videos?.length ? (
                    action.videos.map((vid, vIdx) => (
                      <div className="video-item-row" key={vIdx} title={vid}>
                        <span className="video-badge">Video {vIdx + 1}</span>
                        <span className="video-filename">{fileName(vid)}</span>
                        <div className="video-item-actions">
                          <button
                            className="video-move-btn"
                            disabled={vIdx === 0}
                            onClick={() => moveVideo(index, vIdx, vIdx - 1)}
                            title="Đẩy video này lên trước"
                          >
                            <ArrowUp size={11} />
                          </button>
                          <button
                            className="video-move-btn"
                            disabled={vIdx === action.videos.length - 1}
                            onClick={() => moveVideo(index, vIdx, vIdx + 1)}
                            title="Đẩy video này xuống sau"
                          >
                            <ArrowDown size={11} />
                          </button>
                          <button
                            className="video-play-btn"
                            onClick={() => post("/api/queue/test", { gift: action.id, videoIndex: vIdx })}
                            title={`Phát thử Video ${vIdx + 1}`}
                          >
                            <Play size={11} fill="currentColor" /> Phát thử
                          </button>
                          <button
                            className="video-remove-btn"
                            onClick={() => removeVideoFromAction(index, vIdx)}
                            title={`Gỡ Video ${vIdx + 1}`}
                          >
                            <X size={12} />
                          </button>
                        </div>
                      </div>
                    ))
                  ) : (
                    <span className="no-file-notice">Chưa gán video nào cho hành động này</span>
                  )}
                </div>

                <div className="action-picker-buttons" style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "8px" }}>
                  <button className="media-picker-btn" onClick={() => pickVideo(index)}>
                    <FolderOpen size={13} /> {action.videos?.length ? "+ Gán thêm video..." : "Gán video..."}
                  </button>
                  <button className="media-picker-btn" onClick={() => pickFolder(index)} title="Chọn toàn bộ thư mục chứa video">
                    <FolderOpen size={13} /> + Thêm thư mục...
                  </button>
                </div>
              </div>

              {/* Audio Section */}
              <div className="action-media-section">
                <div className="action-section-title">
                  <Music2 size={14} />
                  <span>ÂM THANH (AUDIO)</span>
                </div>
                <div className="action-file-chips">
                  {action.sound ? (
                    <span className="file-chip sound-chip" title={action.sound}>
                      <span className="chip-name">{fileName(action.sound)}</span>
                      <button
                        className="chip-remove"
                        onClick={() => removeAudioFromAction(index)}
                        title="Gỡ audio"
                      >
                        <X size={12} />
                      </button>
                    </span>
                  ) : (
                    <span className="no-file-notice">Mặc định theo video</span>
                  )}
                </div>
                <button className="media-picker-btn" onClick={() => pickAudio(index)}>
                  <Music2 size={13} /> {action.sound ? "Thay đổi audio..." : "Gán audio..."}
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

