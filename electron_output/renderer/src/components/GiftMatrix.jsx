import { Check, CircleAlert, LoaderCircle, Play, Plus, RefreshCw, Search, Trash2, Video } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";

const COMMON_GIFTS = [
  ["rose", "🌹", "Rose", 1], ["tiktok", "🎵", "TikTok", 1], ["ice cream", "🍦", "Ice Cream", 1],
  ["finger heart", "🫰", "Finger Heart", 5], ["doughnut", "🍩", "Doughnut", 30], ["perfume", "🧴", "Perfume", 20],
  ["paper crane", "📜", "Paper Crane", 99], ["sunglasses", "🕶️", "Sunglasses", 199], ["hand heart", "🫶", "Hand Heart", 100],
  ["cap", "🧢", "Cap", 99], ["lion", "🦁", "Lion", 29999], ["sports car", "🏎️", "Sports Car", 7000],
  ["spaceship", "🚀", "Spaceship", 20000], ["dragon", "🐉", "Dragon", 25999], ["universe", "🌌", "TikTok Universe", 34999],
].map(([key, emoji, name, diamonds]) => ({ id: key, key, emoji, name, diamonds }));

const EVENT_TYPES = [
  { id: "gift", icon: "🎁", label: "Quà tặng", shortLabel: "Quà", description: "Khi người xem gửi một quà cụ thể" },
  { id: "follow", icon: "➕", label: "Theo dõi kênh", shortLabel: "Follow", description: "Khi có người theo dõi mới" },
  { id: "like", icon: "❤️", label: "Lượt thích", shortLabel: "Like", description: "Khi một đợt like đạt ngưỡng" },
  { id: "share", icon: "↗️", label: "Chia sẻ LIVE", shortLabel: "Share", description: "Khi người xem chia sẻ phiên LIVE" },
  { id: "comment", icon: "💬", label: "Bình luận", shortLabel: "Comment", description: "Khi bình luận chứa từ khóa" },
  { id: "join", icon: "👋", label: "Vào phòng", shortLabel: "Join", description: "Khi người xem vào phòng LIVE" },
  { id: "subscribe", icon: "⭐", label: "Đăng ký LIVE", shortLabel: "Subscribe", description: "Khi có người đăng ký LIVE" },
];

const eventDefinition = (eventType) => EVENT_TYPES.find((item) => item.id === eventType) || EVENT_TYPES[0];
const normalizedCondition = (eventType, condition) => {
  if (eventType === "like") return String(Math.max(1, Number.parseInt(condition || "1", 10) || 1));
  return String(condition || "").trim().toLowerCase();
};
const triggerKeyFor = (eventType, condition) => eventType === "gift"
  ? normalizedCondition(eventType, condition)
  : `@${eventType}:${normalizedCondition(eventType, condition) || "*"}`;
const eventLabelFor = (eventType, condition, gift) => {
  if (eventType === "gift") return `Quà: ${gift?.name || condition}`;
  if (eventType === "comment") return `Bình luận chứa “${condition}”`;
  if (eventType === "like") return `Ít nhất ${condition || 1} lượt thích`;
  return eventDefinition(eventType).label;
};
const actionIdForEvent = (eventType, condition, actions) => {
  const slug = String(condition || eventType || "action").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || eventType;
  const base = eventType === "gift" ? `gift_${slug}` : `trigger_${eventType}_${slug}`;
  let candidate = base;
  let suffix = 2;
  while (actions.some((action) => action.id === candidate)) {
    candidate = `${base}_${suffix}`;
    suffix += 1;
  }
  return candidate;
};

export function GiftMatrix({ mappings, setMappings, actions, setActions, post, onNotice, onManageVideos, status }) {
  const mappingsRef = useRef(mappings);
  const syncRef = useRef({ saving: false, pending: null });
  const [catalog, setCatalog] = useState([]);
  const [search, setSearch] = useState("");
  const [eventType, setEventType] = useState("gift");
  const [condition, setCondition] = useState("");
  const [selectedGift, setSelectedGift] = useState(null);
  const [selectedVideoPath, setSelectedVideoPath] = useState("");
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [syncState, setSyncState] = useState("ready");
  const [videoPickerOpen, setVideoPickerOpen] = useState(false);

  useEffect(() => { mappingsRef.current = mappings; }, [mappings]);
  useEffect(() => { api.get("/api/gifts").then((result) => setCatalog(result.items || [])).catch(() => {}); }, []);

  const flush = async () => {
    const sync = syncRef.current;
    if (sync.saving || !sync.pending) return;
    const items = sync.pending;
    sync.pending = null;
    sync.saving = true;
    setSyncState("saving");
    try {
      const saved = await post("/api/mappings", { items });
      if (!sync.pending) {
        mappingsRef.current = saved;
        setMappings(saved);
        setSyncState("ready");
      }
    } catch (error) {
      setSyncState("error");
      onNotice(`Không thể áp dụng: ${error.message}`, "error");
    } finally {
      sync.saving = false;
      if (sync.pending) void flush();
    }
  };

  const changeMappings = (transform) => {
    const next = transform(mappingsRef.current);
    mappingsRef.current = next;
    setMappings(next);
    syncRef.current.pending = next;
    void flush();
  };

  const refreshCatalog = async () => {
    setCatalogLoading(true);
    try {
      const result = await post("/api/gifts/refresh");
      setCatalog(result.items || []);
      onNotice(`Đã tải ${result.items?.length || 0} quà từ TikTok`);
    } catch (error) {
      onNotice(error.message, "error");
    } finally {
      setCatalogLoading(false);
    }
  };

  const selectEventType = (nextType) => {
    setEventType(nextType);
    setCondition(nextType === "like" ? "10" : "");
    setSelectedGift(null);
    setSelectedVideoPath("");
    setVideoPickerOpen(false);
  };

  const source = catalog.length ? catalog : COMMON_GIFTS;
  const selectedCondition = eventType === "gift" ? selectedGift?.key || "" : normalizedCondition(eventType, condition);
  const eventReady = eventType === "gift"
    ? Boolean(selectedGift)
    : eventType === "comment"
      ? Boolean(condition.trim())
      : eventType === "like"
        ? Number.isInteger(Number(condition)) && Number(condition) >= 1
        : true;
  const selectedKey = eventReady ? triggerKeyFor(eventType, selectedCondition) : "";
  const selectedMapping = selectedKey
    ? mappings.find((item) => (item.trigger_key || item.gift) === selectedKey)
    : null;
  const selectedDefinition = eventDefinition(eventType);
  const selectedLabel = eventLabelFor(eventType, selectedCondition, selectedGift);

  const assignToLive = async () => {
    if (eventType === "gift" && !selectedGift) return onNotice("Hãy chọn một quà TikTok", "error");
    if (eventType === "comment" && !condition.trim()) return onNotice("Hãy nhập từ khóa bình luận", "error");
    if (eventType === "like" && (!Number.isInteger(Number(condition)) || Number(condition) < 1)) return onNotice("Ngưỡng like phải là số nguyên từ 1 trở lên", "error");
    if (!selectedVideoPath) return onNotice("Hãy chọn video hành động trước", "error");

    const existingIndex = mappings.findIndex((item) => (item.trigger_key || item.gift) === selectedKey);
    const existingMapping = existingIndex >= 0 ? mappings[existingIndex] : null;
    const existingActionId = existingMapping?.action_id || existingMapping?.action || "";
    const existingAction = actions.find((action) => action.id === existingActionId);
    const actionId = existingAction?.id || actionIdForEvent(eventType, selectedCondition, actions);
    const nextVideos = [...new Set([...(existingAction?.videos || []).filter(Boolean), selectedVideoPath])];
    const actionName = existingAction?.name && existingAction.name !== "Custom Video"
      ? existingAction.name
      : `${selectedLabel} Action`;
    const nextActions = existingAction
      ? actions.map((action) => action.id === actionId ? { ...action, name: actionName, videos: nextVideos } : action)
      : [...actions, { id: actionId, name: actionName, videos: nextVideos, sound: existingMapping?.sound || "" }];
    const mapping = {
      ...(existingMapping || {}),
      gift: selectedKey,
      trigger_key: selectedKey,
      event_type: eventType,
      condition: selectedCondition,
      action: actionId,
      action_id: actionId,
      action_name: actionName,
      priority: existingMapping?.priority || 1,
      cooldown_seconds: existingMapping?.cooldown_seconds || 0,
      enabled: existingMapping?.enabled !== false,
      videos: nextVideos,
      sound: existingMapping?.sound || "",
    };
    const nextMappings = existingMapping
      ? mappings.map((item, index) => index === existingIndex ? mapping : item)
      : [...mappings, mapping];
    try {
      const saved = await post("/api/catalog", { actions: nextActions, mappings: nextMappings });
      setActions(saved.actions);
      mappingsRef.current = saved.mappings;
      setMappings(saved.mappings);
      setSelectedVideoPath("");
      onNotice(existingMapping ? `Đã cập nhật ${selectedLabel}` : `Đã thêm ${selectedLabel} vào LIVE`);
    } catch (error) {
      onNotice(`Không thể gán video: ${error.message}`, "error");
    }
  };

  const assignVideo = (path) => {
    setSelectedVideoPath(path);
    setVideoPickerOpen(false);
    onNotice(`Đã chọn ${path.split(/[\\/]/).at(-1)} cho ${selectedLabel}`);
  };

  const removeMapping = (index) => changeMappings((current) => current.filter((_, itemIndex) => itemIndex !== index));
  const updateMapping = (index, patch) => changeMappings((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
  const visibleGifts = source.filter((gift) => gift.name.toLowerCase().includes(search.trim().toLowerCase()));
  const managedVideos = [...new Set([...actions.flatMap((action) => action.videos || []), ...JSON.parse(window.localStorage.getItem("tiktok-live-action-videos-v3") || "[]")].filter(Boolean))];
  const selectedActionId = selectedMapping?.action_id || selectedMapping?.action;
  const isLive = Boolean(status?.running && status?.tiktok_connected);
  const canAssign = Boolean(eventReady && selectedVideoPath);

  return (
    <section className="gift-mapping-studio">
      <aside className="mapping-builder">
        <div className="builder-heading"><span>THÊM TƯƠNG TÁC TIKTOK</span><h2>Chọn sự kiện kích hoạt</h2></div>
        <div className="event-type-grid" role="list" aria-label="Loại tương tác TikTok">
          {EVENT_TYPES.map((item) => <button type="button" role="listitem" key={item.id} className={eventType === item.id ? "selected" : ""} onClick={() => selectEventType(item.id)} title={item.description}><span>{item.icon}</span><strong>{item.shortLabel}</strong></button>)}
        </div>

        {eventType === "gift" ? <>
          <div className="catalog-title"><div><strong>Chọn quà TikTok</strong><small>{catalog.length ? "Danh sách của room đang live" : "Quà phổ thông"}</small></div><button onClick={refreshCatalog} disabled={catalogLoading}><RefreshCw size={13} className={catalogLoading ? "sync-spinner" : ""} /> Tải lại</button></div>
          <label className="catalog-search"><Search size={13} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Tìm Rose, Ice Cream…" /></label>
          <div className="gift-picker-grid">
            {visibleGifts.map((gift) => <button type="button" key={gift.id} className={selectedGift?.key === gift.key ? "selected" : ""} onClick={() => setSelectedGift(gift)}>
              {gift.image_url ? <img src={gift.image_url} alt="" /> : <span>{gift.emoji}</span>}<strong>{gift.name}</strong><small>💎 {gift.diamonds}</small>
            </button>)}
          </div>
        </> : <div className="event-condition-card">
          <div className="event-condition-icon">{selectedDefinition.icon}</div>
          <div><strong>{selectedDefinition.label}</strong><small>{selectedDefinition.description}</small></div>
          {eventType === "comment" ? <label><span>Từ khóa cần có</span><input value={condition} onChange={(event) => setCondition(event.target.value)} placeholder="Ví dụ: xin chào" /></label> : null}
          {eventType === "like" ? <label><span>Ngưỡng like mỗi sự kiện</span><input type="number" min="1" step="1" value={condition} onChange={(event) => setCondition(event.target.value)} /></label> : null}
          {!['comment', 'like'].includes(eventType) ? <p>Sự kiện sẽ kích hoạt với mọi người xem thực hiện hành động này.</p> : null}
        </div>}

        <label className="builder-field action-picker"><small>Video hành động</small><select value={selectedVideoPath} onChange={(event) => setSelectedVideoPath(event.target.value)}><option value="">Chọn video…</option>{managedVideos.map((path) => <option value={path} key={path}>{path.split(/[\\/]/).at(-1)}</option>)}</select></label>
        {eventReady ? <div className="gift-video-assignment"><span>{selectedMapping ? "CẬP NHẬT VIDEO CHO" : "GÁN VIDEO CHO"}</span><strong>{selectedDefinition.icon} {selectedLabel}</strong><small>{selectedVideoPath ? selectedVideoPath.split(/[\\/]/).at(-1) : selectedMapping?.available_video_count ? `Đang có ${selectedMapping.available_video_count} video` : "Chọn video trước"}</small><div><button onClick={() => setVideoPickerOpen((current) => !current)}><Video size={13} /> Gán video</button><button onClick={() => onManageVideos?.(selectedActionId)}>Quản lý</button></div>{videoPickerOpen ? <div className="managed-video-picker">{managedVideos.length ? managedVideos.map((path) => <button key={path} onClick={() => assignVideo(path)}>{path.split(/[\\/]/).at(-1)}</button>) : <p>Chưa có video. Hãy thêm ở tab Video hành động.</p>}</div> : null}</div> : null}
        <div className="builder-actions"><button onClick={() => onManageVideos?.(selectedActionId)}><Plus size={14} /> Thêm video</button><button className="assign-button" onClick={assignToLive} disabled={!canAssign}><Check size={14} /> {selectedMapping ? "Cập nhật LIVE" : "Gán vào LIVE"}</button></div>
      </aside>

      <main className="mapping-list-panel">
        <div className="mapping-list-heading"><div><span>LUẬT TƯƠNG TÁC TIKTOK</span><h2>{mappings.length} quy tắc</h2></div><span className={`mapping-sync ${syncState}`}>{syncState === "saving" ? <LoaderCircle size={13} className="sync-spinner" /> : syncState === "error" ? <CircleAlert size={13} /> : <Check size={13} />}{syncState === "saving" ? "Đang áp dụng" : syncState === "error" ? "Lỗi đồng bộ" : isLive ? "Đang nhận sự kiện LIVE" : "Đã đồng bộ"}</span></div>
        <div className="interaction-summary">
          {EVENT_TYPES.map((type) => <span key={type.id}><b>{type.icon}</b>{mappings.filter((item) => (item.event_type || "gift") === type.id).length} {type.shortLabel}</span>)}
        </div>
        <div className="mapping-rows">
          {mappings.map((item, index) => {
            const itemEventType = item.event_type || "gift";
            const key = item.condition || item.gift;
            const gift = itemEventType === "gift" ? source.find((candidate) => candidate.key === key) : null;
            const definition = eventDefinition(itemEventType);
            const actionId = item.action_id || item.action;
            const action = actions.find((candidate) => candidate.id === actionId);
            const label = item.event_label || eventLabelFor(itemEventType, key, gift);
            return <article className={`compact-mapping-row event-${itemEventType}`} key={item.trigger_key || `${key}-${index}`}>
              <label className="mapping-toggle"><input type="checkbox" checked={item.enabled !== false} onChange={(event) => updateMapping(index, { enabled: event.target.checked })} /><i /></label>
              <div className="mapping-gift-icon">{gift?.image_url ? <img src={gift.image_url} alt="" /> : gift?.emoji || definition.icon}</div>
              <div className="mapping-copy"><strong>{label}</strong><small>→ {action?.name || item.action_name || "Chưa chọn hành động"} · ưu tiên {item.priority || 1}{item.cooldown_seconds ? ` · nghỉ ${item.cooldown_seconds}s` : ""}{gift ? ` · 💎 ${gift.diamonds || "—"}` : ""}</small></div>
              <button className="row-test" disabled={!item.active} onClick={() => post("/api/triggers/test", { trigger_key: item.trigger_key || item.gift })}><Play size={13} fill="currentColor" /> Thử</button>
              <button className="row-delete" onClick={() => removeMapping(index)} title="Xóa quy tắc"><Trash2 size={14} /></button>
            </article>;
          })}
          {!mappings.length ? <div className="mapping-empty">Chọn một loại tương tác bên trái, chọn video rồi bấm <strong>Gán vào LIVE</strong>.</div> : null}
        </div>
      </main>
    </section>
  );
}
