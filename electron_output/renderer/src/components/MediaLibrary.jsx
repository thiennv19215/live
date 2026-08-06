import { FolderPlus, PlaySquare, Trash2, Video } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "tiktok-live-media-library";
const fileName = (path = "") => path.split(/[\\/]/).at(-1) || path;

function loadSavedLibrary() {
  try {
    const value = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

export function MediaLibrary({ config, setConfig, mappings, setMappings, post, onNotice }) {
  const [savedPaths, setSavedPaths] = useState(loadSavedLibrary);
  const [gift, setGift] = useState("");

  useEffect(() => {
    if (!gift && mappings?.length) setGift(mappings[0].gift);
  }, [gift, mappings]);

  const paths = useMemo(() => {
    return [...new Set([config?.idle_video_path, ...savedPaths].filter(Boolean))];
  }, [config?.idle_video_path, savedPaths]);

  const addVideos = async () => {
    const selected = await window.desktop?.pickMedia?.({ title: "Thêm video vào thư viện", multiple: true });
    if (!selected?.length) return;
    const next = [...new Set([...savedPaths, ...selected])];
    setSavedPaths(next);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    onNotice(`Đã thêm ${selected.length} video vào thư viện`);
  };

  const remove = (path) => {
    const next = savedPaths.filter((item) => item !== path);
    setSavedPaths(next);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  };

  const setIdle = async (path) => {
    await post("/api/media/idle", { path });
    setConfig((current) => ({ ...current, idle_video_path: path }));
    onNotice(`Đã đặt ${fileName(path)} làm video nền`);
  };

  const setAction = async (path) => {
    if (!gift) return onNotice("Chưa có quà để gán action", "error");
    const items = mappings.map((item) => item.gift === gift ? { ...item, action: path } : item);
    const saved = await post("/api/mappings", { items });
    setMappings(saved);
    onNotice(`Đã gán ${fileName(path)} cho ${gift}`);
  };

  return (
    <section className="media-library-panel">
      <div className="media-library-heading">
        <div><Video size={18} /><div><span>MEDIA LIBRARY</span><h2>Thư viện video</h2></div></div>
        <button onClick={addVideos}><FolderPlus size={16} /> Thêm video</button>
      </div>
      <label className="library-gift-select"><span>Gán action cho quà</span><select value={gift} onChange={(event) => setGift(event.target.value)}>{(mappings || []).map((item) => <option key={item.gift}>{item.gift}</option>)}</select></label>
      <div className="media-library-list">
        {paths.length ? paths.map((path) => (
          <article className="media-library-item" key={path}>
            <div className="media-file-icon"><PlaySquare size={19} /></div>
            <div className="media-file-copy"><strong title={path}>{fileName(path)}</strong><span title={path}>{path}</span></div>
            <div className="media-file-actions">
              <button onClick={() => setIdle(path)}>Nền</button>
              <button onClick={() => setAction(path)}>Action</button>
              {savedPaths.includes(path) ? <button className="remove" onClick={() => remove(path)} title="Bỏ khỏi thư viện"><Trash2 size={13} /></button> : null}
            </div>
          </article>
        )) : <div className="empty-library"><Video size={28} /><span>Chưa có video</span><button onClick={addVideos}>Thêm video đầu tiên</button></div>}
      </div>
    </section>
  );
}
