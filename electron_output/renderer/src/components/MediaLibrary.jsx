import { FolderPlus, Play, PlaySquare, Trash2, Video, Volume2, VolumeX } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "tiktok-live-action-videos-v3";
const fileName = (path = "") => path.split(/[\\/]/).at(-1) || path;
const normalizedPath = (path = "") => path.replaceAll("\\", "/").toLowerCase();
const load = (key, fallback) => { try { return JSON.parse(window.localStorage.getItem(key) || JSON.stringify(fallback)); } catch { return fallback; } };

export function MediaLibrary({ config, setConfig, actions, setActions, post, onNotice, targetActionId, onTargetActionChange }) {
  const [savedPaths, setSavedPaths] = useState(() => load(STORAGE_KEY, []));
  const selectedActionId = targetActionId || actions?.[0]?.id || "";

  useEffect(() => { if (!targetActionId && actions?.length) onTargetActionChange?.(actions[0].id); }, [actions, onTargetActionChange, targetActionId]);
  const paths = useMemo(() => [...new Set([...savedPaths, ...(actions || []).flatMap((action) => action.videos || [])].filter(Boolean))], [actions, savedPaths]);
  const selectedAction = actions?.find((action) => action.id === selectedActionId);

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
    await post("/api/media/preview", { path, action_id: selectedActionId });
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

  const toggleIdleVideoMute = async () => {
    try {
      const next = { ...config, idle_video_muted: !config?.idle_video_muted };
      const saved = await post("/api/config", next);
      setConfig(saved);
      onNotice(saved.idle_video_muted ? "Đã tắt âm thanh video nền" : "Đã bật âm thanh video nền");
    } catch (error) {
      onNotice(`Không thể đổi âm thanh video nền: ${error.message}`, "error");
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
          return <article className="action-video-row" key={path}>
            <div className="action-video-thumb"><PlaySquare size={24} /></div>
            <div className="action-video-fields">
              <strong className="action-video-name">{fileName(path)}</strong>
              <small>Video được phát đủ thời lượng gốc và theo đúng thứ tự sự kiện nhận được.</small>
              <span className="action-video-path" title={path}>{path}</span>
            </div>
            <div className="action-video-buttons">
              <button className={normalizedPath(path) === normalizedPath(config?.idle_video_path) ? "idle active" : "idle"} onClick={() => setIdle(path)}>{normalizedPath(path) === normalizedPath(config?.idle_video_path) ? "Đang là nền" : "Đặt nền"}</button>
              {normalizedPath(path) === normalizedPath(config?.idle_video_path) ? <button className={config?.idle_video_muted ? "video-muted active" : "video-muted"} onClick={toggleIdleVideoMute}>{config?.idle_video_muted ? <VolumeX size={13} /> : <Volume2 size={13} />}{config?.idle_video_muted ? "Bật âm nền" : "Tắt âm nền"}</button> : null}
              <button onClick={() => preview(path)}><Play size={13} fill="currentColor" /> Phát thử</button>
              <button className="delete" onClick={() => remove(path)}><Trash2 size={13} /> Xóa</button>
            </div>
          </article>;
        })}
        {!paths.length ? <div className="action-video-empty"><Video size={32} /><strong>Chưa có video hành động</strong><span>Thêm video để bắt đầu cấu hình hiệu ứng live.</span></div> : null}
      </div>
      <div className="action-video-footer">Phát thử sẽ dùng hành động: <strong>{selectedAction?.name || "Chưa chọn"}</strong></div>
    </section>
  );
}
