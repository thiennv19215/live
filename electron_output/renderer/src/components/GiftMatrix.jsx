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

const fileCount = (action) => action?.available_video_count ?? action?.videos?.length ?? 0;

export function GiftMatrix({ mappings, setMappings, actions, setActions, post, onNotice, onManageVideos, status }) {
  const mappingsRef = useRef(mappings);
  const syncRef = useRef({ saving: false, pending: null });
  const [catalog, setCatalog] = useState([]);
  const [search, setSearch] = useState("");
  const [selectedGift, setSelectedGift] = useState("");
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

  const addMapping = (gift = selectedGift) => {
    if (!gift) return onNotice("Hãy chọn một quà TikTok", "error");
    if (!selectedVideoPath) return onNotice("Hãy chọn video hành động trước", "error");
    if (mappings.some((item) => (item.event_type || "gift") === "gift" && (item.condition || item.gift) === gift.key)) {
      return onNotice(`${gift.name} đã có trong mapping`);
    }
    changeMappings((current) => [...current, {
      gift: gift.key, trigger_key: gift.key, event_type: "gift", condition: gift.key,
      action: selectedVideoPath, action_id: "", action_name: selectedVideoPath.split(/[\\/]/).at(-1),
      priority: 1, cooldown_seconds: 0, enabled: true, videos: [selectedVideoPath], sound: "",
    }]);
    setSelectedGift(gift);
    onNotice(`Đã thêm ${gift.name} vào danh sách mapping`);
  };

  const assignVideo = (path) => {
    setSelectedVideoPath(path);
    setVideoPickerOpen(false);
    if (selectedGift) onNotice(`Đã chọn ${path.split(/[\\/]/).at(-1)} cho ${selectedGift.name}`);
  };

  const removeMapping = (index) => changeMappings((current) => current.filter((_, itemIndex) => itemIndex !== index));
  const updateMapping = (index, patch) => changeMappings((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
  const source = catalog.length ? catalog : COMMON_GIFTS;
  const visibleGifts = source.filter((gift) => gift.name.toLowerCase().includes(search.trim().toLowerCase()));
  const managedVideos = [...new Set([...actions.flatMap((action) => action.videos || []), ...JSON.parse(window.localStorage.getItem("tiktok-live-action-videos-v3") || "[]")])];
  const isLive = Boolean(status?.running && status?.tiktok_connected);

  return (
    <section className="gift-mapping-studio">
      <aside className="mapping-builder">
        <div className="builder-heading"><span>THÊM QUÀ HOẶC LỆNH</span><h2>Chọn quà TikTok</h2></div>
        <label className="builder-field"><small>Loại</small><select><option>Quà</option></select></label>
        <div className="catalog-title"><div><strong>Chọn quà TikTok</strong><small>{catalog.length ? "Danh sách của room đang live" : "Quà phổ thông"}</small></div><button onClick={refreshCatalog} disabled={catalogLoading}><RefreshCw size={13} className={catalogLoading ? "sync-spinner" : ""} /> Tải lại</button></div>
        <label className="catalog-search"><Search size={13} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Tìm Rose, Ice Cream…" /></label>
        <div className="gift-picker-grid">
          {visibleGifts.map((gift) => <button key={gift.id} className={selectedGift?.key === gift.key ? "selected" : ""} onClick={() => addMapping(gift)}>
            {gift.image_url ? <img src={gift.image_url} alt="" /> : <span>{gift.emoji}</span>}<strong>{gift.name}</strong><small>💎 {gift.diamonds}</small>
          </button>)}
        </div>
        <label className="builder-field action-picker"><small>Video hành động</small><select value={selectedVideoPath} onChange={(event) => setSelectedVideoPath(event.target.value)}><option value="">Chọn video…</option>{managedVideos.map((path) => <option value={path} key={path}>{path.split(/[\\/]/).at(-1)}</option>)}</select></label>
        {selectedGift ? <div className="gift-video-assignment"><span>GÁN VIDEO CHO</span><strong>{selectedGift.emoji || "🎁"} {selectedGift.name}</strong><small>{selectedVideoPath ? selectedVideoPath.split(/[\\/]/).at(-1) : "Chọn video trước"}</small><div><button onClick={() => setVideoPickerOpen((current) => !current)}><Video size={13} /> Gán video</button><button onClick={() => onManageVideos?.()} >Quản lý</button></div>{videoPickerOpen ? <div className="managed-video-picker">{managedVideos.length ? managedVideos.map((path) => <button key={path} onClick={() => assignVideo(path)}>{path.split(/[\\/]/).at(-1)}</button>) : <p>Chưa có video. Hãy thêm ở tab Video hành động.</p>}</div> : null}</div> : null}
        <div className="builder-actions"><button onClick={() => onManageVideos?.()}><Plus size={14} /> Thêm video</button><button className="assign-button" onClick={() => addMapping()} disabled={!selectedGift || !selectedVideoPath}><Check size={14} /> Gán vào live</button></div>
      </aside>

      <main className="mapping-list-panel">
        <div className="mapping-list-heading"><div><span>DANH SÁCH MAPPING</span><h2>{mappings.length} quy tắc</h2></div><span className={`mapping-sync ${syncState}`}>{syncState === "saving" ? <LoaderCircle size={13} className="sync-spinner" /> : syncState === "error" ? <CircleAlert size={13} /> : <Check size={13} />}{syncState === "saving" ? "Đang áp dụng" : syncState === "error" ? "Lỗi đồng bộ" : isLive ? "Đang chạy live" : "Đã đồng bộ"}</span></div>
        <div className="mapping-rows">
          {mappings.map((item, index) => {
            const key = item.condition || item.gift;
            const gift = source.find((candidate) => candidate.key === key);
            const actionId = item.action_id || item.action;
            const action = actions.find((candidate) => candidate.id === actionId);
            return <article className="compact-mapping-row" key={item.trigger_key || `${key}-${index}`}>
              <label className="mapping-toggle"><input type="checkbox" checked={item.enabled !== false} onChange={(event) => updateMapping(index, { enabled: event.target.checked })} /><i /></label>
              <div className="mapping-gift-icon">{gift?.image_url ? <img src={gift.image_url} alt="" /> : gift?.emoji || "🎁"}</div>
              <div className="mapping-copy"><strong>Quà: {gift?.name || key}</strong><small>→ {action?.name || item.action_name || "Chưa chọn hành động"} · ưu tiên {item.priority || 1} · 💎 {gift?.diamonds || "—"}</small></div>
              <button className="row-test" disabled={!item.active} onClick={() => post("/api/triggers/test", { trigger_key: item.trigger_key || item.gift })}><Play size={13} fill="currentColor" /> Thử</button>
              <button className="row-delete" onClick={() => removeMapping(index)} title="Xóa mapping"><Trash2 size={14} /></button>
            </article>;
          })}
          {!mappings.length ? <div className="mapping-empty">Chọn quà bên trái, chọn hành động rồi bấm <strong>Gán vào live</strong>.</div> : null}
        </div>
      </main>
    </section>
  );
}
