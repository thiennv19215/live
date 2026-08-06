import { ExternalLink, FolderOpen, Library, MonitorUp, SkipForward, Square, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

const RATIOS = {
  "9:16": [1080, 1920],
  "16:9": [1920, 1080],
  "1:1": [1080, 1080],
  "4:5": [1080, 1350],
};

export function OutputStage({ status, config, setConfig, mappings, setMappings, post, onNotice, showLibrary = true }) {
  const [outputOpen, setOutputOpen] = useState(false);
  const [selectedGift, setSelectedGift] = useState("");
  const ratio = config?.output_ratio || "9:16";
  const [width, height] = RATIOS[ratio];

  useEffect(() => {
    window.desktop?.getOutputStatus?.().then((next) => setOutputOpen(Boolean(next?.open)));
  }, []);

  useEffect(() => {
    if (!selectedGift && mappings?.length) setSelectedGift(mappings[0].gift);
  }, [mappings, selectedGift]);

  const pickIdle = async () => {
    const path = await window.desktop?.pickMedia?.({ title: "Chọn video nền" });
    if (!path) return;
    await post("/api/media/idle", { path });
    setConfig((current) => ({ ...current, idle_video_path: path }));
    onNotice("Đã thay video nền");
  };

  const pickAction = async () => {
    if (!selectedGift) {
      onNotice("Hãy tạo một quà trước khi gán video hành động", "error");
      return;
    }
    const paths = await window.desktop?.pickMedia?.({ title: `Chọn video hành động cho ${selectedGift}`, multiple: true });
    if (!paths?.length) return;
    const items = mappings.map((item) => item.gift === selectedGift ? { ...item, action: paths.join(", ") } : item);
    const saved = await post("/api/mappings", { items });
    setMappings(saved);
    onNotice(`Đã gán ${paths.length} video cho ${selectedGift}`);
  };

  const pickAudio = async () => {
    if (!selectedGift) {
      onNotice("Hãy chọn quà cần gán audio", "error");
      return;
    }
    const path = await window.desktop?.pickMedia?.({ title: `Chọn audio cho ${selectedGift}`, kind: "audio" });
    if (!path) return;
    const items = mappings.map((item) => item.gift === selectedGift ? { ...item, sound: path } : item);
    const saved = await post("/api/mappings", { items });
    setMappings(saved);
    onNotice(`Đã gán audio cho ${selectedGift}`);
  };

  const openOutput = async () => {
    if (!status.overlay_url) {
      onNotice("Overlay backend chưa sẵn sàng", "error");
      return;
    }
    await window.desktop?.openOutput?.({ url: status.overlay_url, ratio, width, height });
    setOutputOpen(true);
    onNotice("Output đã sẵn sàng cho TikTok Studio");
  };

  const closeOutput = async () => {
    await window.desktop?.closeOutput?.();
    setOutputOpen(false);
  };

  const changeRatio = async (event) => {
    const output_ratio = event.target.value;
    const next = { ...config, output_ratio };
    setConfig(next);
    await post("/api/config", next);
    if (outputOpen) {
      const [nextWidth, nextHeight] = RATIOS[output_ratio];
      await window.desktop?.openOutput?.({ url: status.overlay_url, ratio: output_ratio, width: nextWidth, height: nextHeight });
    }
  };

  const frameStyle = { aspectRatio: `${width} / ${height}` };
  const current = status.current;

  return (
    <section className={`output-stage ${showLibrary ? "with-library" : "preview-only"}`}>
      <div className="stage-toolbar">
        <div>
          <span>LIVE OUTPUT</span>
          <h2>{current ? `Đang phát: ${current.gift}` : "Video nền đang lặp"}</h2>
        </div>
        <div className="stage-controls">
          {!showLibrary ? <button className="toolbar-action" onClick={() => post("/api/queue/skip")} disabled={!current}><SkipForward size={14} /> Bỏ qua</button> : null}
          {!showLibrary ? <button className="toolbar-action danger" onClick={() => post("/api/queue/clear")}><Trash2 size={14} /> Xóa hàng đợi</button> : null}
          <select value={ratio} onChange={changeRatio} aria-label="Tỉ lệ output">
            {Object.keys(RATIOS).map((item) => <option key={item}>{item}</option>)}
          </select>
          <button className={outputOpen ? "output-live-button" : "output-button"} onClick={openOutput}>
            <MonitorUp size={16} /> {outputOpen ? "Output đang mở" : "Mở output"}
          </button>
          {outputOpen ? <button className="icon-button" onClick={closeOutput} title="Đóng output"><Square size={15} /></button> : null}
        </div>
      </div>

      <div className="stage-body">
        <div className={`preview-frame ratio-${ratio.replace(":", "-")}`} style={frameStyle}>
          {status.overlay_url ? (
            <iframe src={`${status.overlay_url}?fit=contain`} title="Live output preview" />
          ) : (
            <div className="preview-offline">Đang chờ overlay…</div>
          )}
          <div className="preview-corners" aria-hidden="true" />
          <span className="resolution-label">{width} × {height}</span>
        </div>

        {showLibrary ? <div className="playback-console">
          <div className="library-heading">
            <div><Library size={17} /><span>Thư viện media</span></div>
            <button onClick={() => window.desktop?.openVideosFolder?.()} title="Mở thư mục videos"><FolderOpen size={15} /></button>
          </div>
          <div className="now-playing">
            <span className="pulse-dot" />
            <div>
              <span>{current ? "ACTION SOURCE" : "IDLE SOURCE"}</span>
              <strong>{current?.file || config?.idle_video_path?.split(/[\\/]/).at(-1) || "Chưa có media"}</strong>
            </div>
          </div>
          <div className="progress-track"><span style={{ width: `${Math.round(status.progress * 100)}%` }} /></div>
          <div className="progress-meta">
            <span>{current ? `${status.remaining.toFixed(1)} giây còn lại` : "LOOPING"}</span>
            <span>{Math.round(status.progress * 100)}%</span>
          </div>
          <div className="stage-media-controls">
            <button onClick={pickIdle}><FolderOpen size={15} /><span><small>VIDEO NỀN</small>{config?.idle_video_path?.split(/[\\/]/).at(-1) || "Chọn video"}</span></button>
            <div className="action-media-control">
              <select value={selectedGift} onChange={(event) => setSelectedGift(event.target.value)} aria-label="Quà cần gán video">
                {(mappings || []).map((item) => <option value={item.gift} key={item.gift}>{item.gift}</option>)}
              </select>
              <button onClick={pickAction}><FolderOpen size={15} /><span><small>VIDEO HÀNH ĐỘNG</small>Chọn video</span></button>
            </div>
            <button onClick={pickAudio}><FolderOpen size={15} /><span><small>AUDIO HÀNH ĐỘNG</small>{mappings?.find((item) => item.gift === selectedGift)?.sound?.split(/[\\/]/).at(-1) || "Chọn audio"}</span></button>
          </div>
          <button className="skip-button" onClick={() => post("/api/queue/skip")} disabled={!current}>
            <SkipForward size={17} /> Bỏ qua action hiện tại
          </button>
          <button className="link-button" onClick={() => navigator.clipboard?.writeText(status.overlay_url || "")}>
            <ExternalLink size={15} /> Copy Browser Overlay URL
          </button>
        </div> : null}
      </div>
    </section>
  );
}
