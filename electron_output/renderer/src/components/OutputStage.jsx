import { ExternalLink, MonitorUp, SkipForward, Square } from "lucide-react";
import { useEffect, useState } from "react";

const RATIOS = {
  "9:16": [1080, 1920],
  "16:9": [1920, 1080],
  "1:1": [1080, 1080],
  "4:5": [1080, 1350],
};

export function OutputStage({ status, config, setConfig, post, onNotice }) {
  const [outputOpen, setOutputOpen] = useState(false);
  const ratio = config?.output_ratio || "9:16";
  const [width, height] = RATIOS[ratio];

  useEffect(() => {
    window.desktop?.getOutputStatus?.().then((next) => setOutputOpen(Boolean(next?.open)));
  }, []);

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
    <section className="output-stage">
      <div className="stage-toolbar">
        <div>
          <span>LIVE OUTPUT</span>
          <h2>{current ? `Đang phát: ${current.gift}` : "Video nền đang lặp"}</h2>
        </div>
        <div className="stage-controls">
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
            <iframe src={`${status.overlay_url}?muted=1`} title="Live output preview" />
          ) : (
            <div className="preview-offline">Đang chờ overlay…</div>
          )}
          <div className="preview-corners" aria-hidden="true" />
          <span className="resolution-label">{width} × {height}</span>
        </div>

        <div className="playback-console">
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
          <button className="skip-button" onClick={() => post("/api/queue/skip")} disabled={!current}>
            <SkipForward size={17} /> Bỏ qua action hiện tại
          </button>
          <button className="link-button" onClick={() => navigator.clipboard?.writeText(status.overlay_url || "")}>
            <ExternalLink size={15} /> Copy Browser Overlay URL
          </button>
        </div>
      </div>
    </section>
  );
}
