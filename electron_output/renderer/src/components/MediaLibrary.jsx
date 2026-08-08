import { FolderPlus, Play, PlaySquare, Trash2, Video } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "tiktok-live-action-videos-v3";
const META_KEY = "tiktok-live-action-video-meta-v1";
const fileName = (path = "") => path.split(/[\\/]/).at(-1) || path;
const normalizedPath = (path = "") => path.replaceAll("\\", "/").toLowerCase();
const load = (key, fallback) => { try { return JSON.parse(window.localStorage.getItem(key) || JSON.stringify(fallback)); } catch { return fallback; } };

export function MediaLibrary({ config, setConfig, actions, setActions, post, onNotice, targetActionId, onTargetActionChange }) {
  const [savedPaths, setSavedPaths] = useState(() => load(STORAGE_KEY, []));
  const [meta, setMeta] = useState(() => load(META_KEY, {}));
  const selectedActionId = targetActionId || actions?.[0]?.id || "";

  useEffect(() => { if (!targetActionId && actions?.length) onTargetActionChange?.(actions[0].id); }, [actions, onTargetActionChange, targetActionId]);
  const paths = useMemo(() => [...new Set([...savedPaths, ...(actions || []).flatMap((action) => action.videos || [])].filter(Boolean))], [actions, savedPaths]);
  const selectedAction = actions?.find((action) => action.id === selectedActionId);
  const saveMeta = (next) => { setMeta(next); window.localStorage.setItem(META_KEY, JSON.stringify(next)); };
  const updateMeta = (path, patch) => saveMeta({ ...meta, [normalizedPath(path)]: { name: fileName(path), priority: 1, volume: 1, timeout: 30, ...meta[normalizedPath(path)], ...patch } });

  const addVideos = async () => {
    const selected = await window.desktop?.pickMedia?.({ title: "Thêm video hành động", multiple: true, copyToLibrary: true });
    if (!selected?.length) return;
    const next = [...new Set([...savedPaths, ...selected])];
    setSavedPaths(next);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    onNotice(`Đã thêm ${selected.length} video`);
  };

  const remove = async (path) => {
    const removesIdle = normalizedPath(path) === normalizedPath(config?.idle_video_path);
    const next = savedPaths.filter((item) => normalizedPath(item) !== normalizedPath(path));
    setSavedPaths(next);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    const items = actions.map((action) => ({
      ...action,
      videos: (action.videos || []).filter((video) => normalizedPath(video) !== normalizedPath(path)),
    }));
    try {
      const saved = await post("/api/actions", { items });
      if (removesIdle) {
        await post("/api/media/idle/clear");
        setConfig((current) => ({ ...current, idle_video_path: "" }));
      }
      setActions(saved);
      onNotice(removesIdle
        ? `Đã xóa ${fileName(path)} và dừng video nền`
        : `Đã gỡ ${fileName(path)} khỏi danh sách và các hành động`);
    } catch (error) {
      setSavedPaths(savedPaths);
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(savedPaths));
      onNotice(`Không thể xóa video: ${error.message}`, "error");
    }
  };

  const preview = async (path) => {
    if (!selectedActionId) return onNotice("Chưa có hành động để phát thử", "error");
    await post("/api/queue/test", { gift: selectedActionId, sender: "Phát thử video" });
    onNotice(`Đang phát thử ${fileName(path)}`);
  };

  const setIdle = async (path) => {
    try {
      await post("/api/media/idle", { path });
      setConfig((current) => ({ ...current, idle_video_path: path }));
      onNotice(`Đã đặt ${fileName(path)} làm video nền`);
    } catch (error) {
      onNotice(`Không thể đặt video nền: ${error.message}`, "error");
    }
  };

  const clearIdle = async () => {
    try {
      await post("/api/media/idle/clear");
      setConfig((current) => ({ ...current, idle_video_path: "" }));
      onNotice("Đã xóa và dừng video nền");
    } catch (error) {
      onNotice(`Không thể xóa video nền: ${error.message}`, "error");
    }
  };

  return (
    <section className="action-video-workspace">
      <div className="action-video-heading"><div><span>VIDEO HÀNH ĐỘNG</span><h2>Video hành động</h2><small>{paths.length}/20 video</small></div><button onClick={addVideos}><FolderPlus size={15} /> Thêm video</button></div>
      <div className="idle-video-status">
        <span>VIDEO NỀN ĐANG DÙNG</span>
        <strong>{config?.idle_video_path ? fileName(config.idle_video_path) : "Chưa chọn video nền"}</strong>
        {config?.idle_video_path ? <button onClick={clearIdle}><Trash2 size={12} /> Xóa nền</button> : null}
      </div>
      <button className="video-dropzone" onClick={addVideos}>Kéo video vào đây hoặc bấm “Thêm video”</button>
      <div className="action-video-list">
        {paths.map((path) => {
          const info = { name: fileName(path), priority: 1, volume: 1, timeout: 30, ...meta[normalizedPath(path)] };
          return <article className="action-video-row" key={path}>
            <div className="action-video-thumb"><PlaySquare size={24} /></div>
            <div className="action-video-fields">
              <label className="video-name-field"><small>Tên</small><input value={info.name} onChange={(event) => updateMeta(path, { name: event.target.value })} /></label>
              <div className="video-settings-row">
                <label><small>Ưu tiên</small><input type="number" min="1" max="5" value={info.priority} onChange={(event) => updateMeta(path, { priority: Number(event.target.value) })} /></label>
                <label><small>Âm lượng</small><input type="number" min="0" max="1" step="0.1" value={info.volume} onChange={(event) => updateMeta(path, { volume: Number(event.target.value) })} /></label>
                <label><small>Timeout (giây)</small><input type="number" min="1" value={info.timeout} onChange={(event) => updateMeta(path, { timeout: Number(event.target.value) })} /></label>
              </div>
              <span className="action-video-path" title={path}>{path}</span>
            </div>
            <div className="action-video-buttons"><button className={normalizedPath(path) === normalizedPath(config?.idle_video_path) ? "idle active" : "idle"} onClick={() => setIdle(path)}>{normalizedPath(path) === normalizedPath(config?.idle_video_path) ? "Đang là nền" : "Đặt nền"}</button><button onClick={() => preview(path)}><Play size={13} fill="currentColor" /> Phát thử</button><button className="delete" onClick={() => remove(path)}><Trash2 size={13} /> Xóa</button></div>
          </article>;
        })}
        {!paths.length ? <div className="action-video-empty"><Video size={32} /><strong>Chưa có video hành động</strong><span>Thêm video để bắt đầu cấu hình hiệu ứng live.</span></div> : null}
      </div>
      <div className="action-video-footer">Phát thử sẽ dùng hành động: <strong>{selectedAction?.name || "Chưa chọn"}</strong></div>
    </section>
  );
}
