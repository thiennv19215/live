import { ExternalLink, Eye, EyeOff, FolderOpen, Gift, Library, MonitorUp, Music2, Square, Trash2, Volume2, VolumeX } from "lucide-react";
import { useEffect, useState } from "react";
import { resolveHiddenChange, resolveOutputStatus } from "../../../output-state.mjs";

const GIFT_ICONS = { rose: "🌹", doughnut: "🍩", tiktok: "🎵", lion: "🦁", perfume: "🧴", congratulations: "🎉", "ice cream": "🍦", "finger heart": "🫰", "paper crane": "📜", "sports car": "🏎️", spaceship: "🚀", dragon: "🐉", universe: "🌌" };

const RATIOS = {
  "9:16": [1080, 1920],
  "16:9": [1920, 1080],
  "1:1": [1080, 1080],
  "4:5": [1080, 1350],
};

const FILL_MODES = {
  original: { label: "Đủ video gốc" },
  cover: { label: "Phủ kín khung" },
};

const giftGuideParams = (config, mappings) => {
  const position = config?.gift_panel_position || {};
  const params = new URLSearchParams({
    gift_guide: config?.gift_guide_enabled ? "1" : "0",
    gift_footer: config?.gift_guide_message || "",
    gift_x: String(position.x ?? 4),
    gift_y: String(position.y ?? 20),
    config_api: window.desktop?.backendUrl || "http://127.0.0.1:8766/api/config",
  });
  const gifts = (mappings || [])
    .filter((item) => (item.event_type || "gift") === "gift" && item.enabled !== false)
    .slice(0, 8)
    .map((item) => {
      const gift = item.condition || item.gift;
      return {
        gift: String(gift || "Quà tặng").replace(/\b\w/g, (letter) => letter.toUpperCase()),
        action: item.action_name && item.action_name !== "Custom Video" ? item.action_name : "Kích hoạt hiệu ứng",
        icon: GIFT_ICONS[String(gift || "").toLowerCase()] || "🎁",
      };
    });
  if (gifts.length) params.set("gift_items", JSON.stringify(gifts));
  return params;
};

const outputUrl = (baseUrl, fillMode, config, mappings) => {
  if (!baseUrl) return "";
  const params = giftGuideParams(config, mappings);
  params.set("fit", fillMode === "cover" ? "cover" : "contain");
  params.set("zoom", "1");
  return `${baseUrl}?${params}`;
};
const previewUrl = (baseUrl, fillMode, muted, config, mappings) => {
  if (!baseUrl) return "";
  const params = giftGuideParams(config, mappings);
  params.set("fit", fillMode === "cover" ? "cover" : "contain");
  params.set("muted", muted ? "1" : "0");
  return `${baseUrl}?${params}`;
};
const initialFillMode = () => {
  const saved = window.localStorage.getItem("output-fill-mode");
  // Old releases stored "crop" and applied an artificial 1.16x zoom.
  // Migrate that value to the full, uncropped source view.
  return FILL_MODES[saved] ? saved : "original";
};

export function OutputStage({ status, config, setConfig, mappings, setMappings, post, onNotice, showLibrary = true }) {
  const [outputOpen, setOutputOpen] = useState(false);
  const [outputBusy, setOutputBusy] = useState(false);
  const [outputHidden, setOutputHidden] = useState(() => window.localStorage.getItem("output-hidden-mode") === "true");
  const [previewMuted, setPreviewMuted] = useState(true);
  const [selectedGift, setSelectedGift] = useState("");
  const [fillMode, setFillMode] = useState(initialFillMode);
  const ratio = config?.output_ratio || "9:16";
  const [width, height] = RATIOS[ratio];

  useEffect(() => {
    window.desktop?.getOutputStatus?.()
      .then((next) => {
        const open = Boolean(next?.open);
        setOutputOpen(open);
        setOutputHidden((savedHidden) => resolveOutputStatus(savedHidden, next).hidden);
        if (open) setPreviewMuted(true);
      })
      .catch((error) => onNotice(`Không đọc được trạng thái Output: ${error.message}`, "error"));
    return window.desktop?.onOutputClosed?.(() => setOutputOpen(false));
  }, [onNotice]);

  useEffect(() => {
    setPreviewMuted(true);
  }, []);

  useEffect(() => {
    if (!selectedGift && mappings?.length) setSelectedGift(mappings[0].gift);
  }, [mappings, selectedGift]);

  useEffect(() => {
    const syncPosition = (event) => {
      if (event.origin !== new URL(status.overlay_url || "http://127.0.0.1:8765").origin) return;
      if (event.data?.type !== "gift-layout-position" || !event.data.position) return;
      setConfig((current) => ({ ...current, gift_panel_position: event.data.position }));
    };
    window.addEventListener("message", syncPosition);
    return () => window.removeEventListener("message", syncPosition);
  }, [setConfig, status.overlay_url]);

  const toggleHiddenMode = async (nextHidden) => {
    try {
      const confirmedHidden = outputOpen
        ? resolveHiddenChange(await window.desktop?.setOutputHidden?.(nextHidden))
        : nextHidden;
      setOutputHidden(confirmedHidden);
      window.localStorage.setItem("output-hidden-mode", String(confirmedHidden));
      if (outputOpen) {
        onNotice(confirmedHidden ? "Output đã chuyển sang chạy ngầm" : "Output đã hiện lên màn hình");
      }
    } catch (error) {
      const next = await window.desktop?.getOutputStatus?.().catch(() => null);
      const resolved = resolveOutputStatus(outputHidden, next);
      setOutputOpen(resolved.open);
      setOutputHidden(resolved.hidden);
      onNotice(`Không đổi được chế độ Output: ${error.message}`, "error");
    }
  };

  const pickIdle = async () => {
    const path = await window.desktop?.pickMedia?.({ title: "Chọn video nền", copyToLibrary: true });
    if (!path) return;
    await post("/api/media/idle", { path });
    setConfig((current) => ({ ...current, idle_video_path: path }));
    onNotice("Đã thay video nền");
  };

  const pickAction = async () => {
    if (!selectedGift) {
      onNotice("Hãy tạo một luật sự kiện trước khi gán video hành động", "error");
      return;
    }
    const paths = await window.desktop?.pickMedia?.({ title: `Chọn video hành động cho ${selectedGift}`, multiple: true, copyToLibrary: true });
    if (!paths?.length) return;
    const items = mappings.map((item) => item.gift === selectedGift ? { ...item, action: paths.join(", "), action_id: "", videos: paths } : item);
    const saved = await post("/api/mappings", { items });
    setMappings(saved);
    onNotice(`Đã gán ${paths.length} video cho ${selectedGift}`);
  };

  const pickAudio = async () => {
    if (!selectedGift) {
      onNotice("Hãy chọn luật sự kiện cần gán audio", "error");
      return;
    }
    const path = await window.desktop?.pickMedia?.({ title: `Chọn audio cho ${selectedGift}`, kind: "audio", copyToLibrary: true });
    if (!path) return;
    const items = mappings.map((item) => item.gift === selectedGift ? { ...item, sound: path } : item);
    const saved = await post("/api/mappings", { items });
    setMappings(saved);
    onNotice(`Đã gán audio cho ${selectedGift}`);
  };

  const pickBackgroundMusic = async () => {
    const path = await window.desktop?.pickMedia?.({ title: "Chọn nhạc nền", kind: "audio", copyToLibrary: true });
    if (!path) return;
    const saved = await post("/api/media/background", { path });
    setConfig(saved);
    onNotice("Đã chọn nhạc nền");
  };

  const toggleBackgroundMute = async () => {
    const next = { ...config, background_music_muted: !config?.background_music_muted };
    const saved = await post("/api/config", next);
    setConfig(saved);
    onNotice(saved.background_music_muted ? "Đã tắt tiếng nhạc nền" : "Đã bật tiếng nhạc nền");
  };

  const openOutput = async () => {
    if (outputOpen || outputBusy) return;
    if (!status.overlay_url) {
      onNotice("Overlay backend chưa sẵn sàng", "error");
      return;
    }
    setOutputBusy(true);
    try {
      await window.desktop?.openOutput?.({ url: outputUrl(status.overlay_url, fillMode, config, mappings), ratio, width, height, hidden: outputHidden });
      setOutputOpen(true);
      setPreviewMuted(true);
      onNotice(outputHidden ? "Output đang chạy ngầm (TikTok Studio vẫn bắt bình thường)" : "Output đã sẵn sàng cho TikTok Studio");
    } catch (error) {
      onNotice(`Không mở được Output: ${error.message}`, "error");
    } finally {
      setOutputBusy(false);
    }
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
      await window.desktop?.openOutput?.({ url: outputUrl(status.overlay_url, fillMode, config, mappings), ratio: output_ratio, width: nextWidth, height: nextHeight, hidden: outputHidden });
    }
  };

  const changeFillMode = async (event) => {
    const nextMode = event.target.value;
    setFillMode(nextMode);
    window.localStorage.setItem("output-fill-mode", nextMode);
    if (outputOpen) await window.desktop?.openOutput?.({ url: outputUrl(status.overlay_url, nextMode, config, mappings), ratio, width, height, hidden: outputHidden });
  };

  const toggleGiftGuide = async () => {
    const next = { ...config, gift_guide_enabled: !config?.gift_guide_enabled };
    const saved = await post("/api/config", next);
    setConfig(saved);
    if (outputOpen) {
      await window.desktop?.openOutput?.({ url: outputUrl(status.overlay_url, fillMode, saved, mappings), ratio, width, height, hidden: outputHidden });
    }
    onNotice(saved.gift_guide_enabled ? "Đã hiện hướng dẫn tặng quà trên video" : "Đã ẩn hướng dẫn tặng quà");
  };

  const frameStyle = { aspectRatio: `${width} / ${height}`, "--preview-zoom": 1 };
  const current = status.current;

  return (
    <section className={`output-stage ${showLibrary ? "with-library" : "preview-only"}`}>
      <div className="stage-toolbar">
        <div>
          <span>LIVE OUTPUT</span>
          <h2>
            {current ? (
              <>
                <span className="live-gift-highlight">
                  🎁 <strong>{current.sender || "Người xem"}</strong> đã tặng{" "}
                  <b className="gift-name-tag">{current.gift}</b>
                  {current.count > 1 ? <span className="gift-count-tag"> x{current.count}</span> : null}
                  {current.diamonds > 0 ? <span className="gift-diamond-tag"> (💎{current.diamonds})</span> : null}
                </span>
              </>
            ) : (
              "Video nền đang lặp"
            )}
          </h2>
        </div>
        <div className="stage-controls">
          {!showLibrary ? <button className="toolbar-action danger" onClick={() => post("/api/queue/clear")}><Trash2 size={14} /> Dừng &amp; xóa</button> : null}
          <button
            className={`toolbar-action ${outputHidden ? "active" : ""}`}
            onClick={() => toggleHiddenMode(!outputHidden)}
            title={outputHidden ? "Đang bật chạy ngầm (Cửa sổ ẩn khỏi màn hình)" : "Đang hiện cửa sổ nổi trên màn hình"}
          >
            {outputHidden ? <EyeOff size={14} /> : <Eye size={14} />} {outputHidden ? "Chạy ngầm" : "Hiện cửa sổ"}
          </button>
          <button className="toolbar-action" onClick={() => setPreviewMuted((current) => !current)} title={previewMuted ? "Bật âm preview" : "Tắt âm preview"}>
            {previewMuted ? <VolumeX size={14} /> : <Volume2 size={14} />} {previewMuted ? "Preview tắt âm" : "Âm preview"}
          </button>
          <button className={`toolbar-action gift-guide-toggle ${config?.gift_guide_enabled ? "active" : ""}`} onClick={toggleGiftGuide} title="Bật hoặc tắt lời nhắc tặng quà trên video">
            <Gift size={14} /> {config?.gift_guide_enabled ? "Đang nhắc tặng quà" : "Bật nhắc tặng quà"}
          </button>
          <select value={fillMode} onChange={changeFillMode} aria-label="Cách lấp đầy output">
            {Object.entries(FILL_MODES).map(([value, item]) => <option value={value} key={value}>{item.label}</option>)}
          </select>
          <select value={ratio} onChange={changeRatio} aria-label="Tỉ lệ output">
            {Object.keys(RATIOS).map((item) => <option key={item}>{item}</option>)}
          </select>
          <button className={outputOpen ? (outputHidden ? "output-live-button hidden-mode" : "output-live-button") : "output-button"} onClick={openOutput} disabled={outputOpen || outputBusy}>
            <MonitorUp size={16} /> {outputBusy ? "Đang mở…" : outputOpen ? (outputHidden ? "Output ngầm đang mở" : "Output đang mở") : "Mở output"}
          </button>
          {outputOpen ? <button className="icon-button" onClick={closeOutput} title="Đóng output"><Square size={15} /></button> : null}
        </div>
      </div>

      <div className="background-music-bar">
        <div className="background-music-copy">
          <span className="background-music-icon"><Music2 size={16} /></span>
          <div><small>NHẠC NỀN</small><strong>{config?.background_music_path?.split(/[\\/]/).at(-1) || "Chưa chọn nhạc"}</strong></div>
        </div>
        <div className="background-music-actions">
          <button onClick={pickBackgroundMusic}><FolderOpen size={14} /> Chọn nhạc của tôi</button>
          <button
            className={config?.background_music_muted ? "muted" : ""}
            onClick={toggleBackgroundMute}
            disabled={!config?.background_music_path}
            title={config?.background_music_muted ? "Bật tiếng nhạc nền" : "Tắt tiếng nhạc nền"}
          >
            {config?.background_music_muted ? <VolumeX size={14} /> : <Volume2 size={14} />}
            {config?.background_music_muted ? "Bật tiếng" : "Tắt tiếng"}
          </button>
        </div>
      </div>

      <div className="stage-body">
        <div className={`preview-frame ratio-${ratio.replace(":", "-")} ${outputOpen ? "output-active" : ""}`} style={frameStyle}>
          {outputOpen ? (
            <div className="preview-offline">
              {outputHidden
                ? "Output đang chạy ngầm cho TikTok Studio (Cửa sổ đã ẩn để nhẹ máy)"
                : "Preview đã ẩn vì Output đang mở trên màn hình"}
            </div>
          ) : status.overlay_url ? (
            <iframe src={previewUrl(status.overlay_url, fillMode, previewMuted, config, mappings)} title="Live output preview" />
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
              <select value={selectedGift} onChange={(event) => setSelectedGift(event.target.value)} aria-label="Luật sự kiện cần gán video">
                {(mappings || []).map((item) => <option value={item.gift} key={item.gift}>{item.event_label || item.gift}</option>)}
              </select>
              <button onClick={pickAction}><FolderOpen size={15} /><span><small>VIDEO HÀNH ĐỘNG</small>Chọn video</span></button>
            </div>
            <button onClick={pickAudio}><FolderOpen size={15} /><span><small>AUDIO HÀNH ĐỘNG</small>{mappings?.find((item) => item.gift === selectedGift)?.sound?.split(/[\\/]/).at(-1) || "Chọn audio"}</span></button>
          </div>
          <button className="link-button" onClick={() => navigator.clipboard?.writeText(status.overlay_url || "")}>
            <ExternalLink size={15} /> Copy Browser Overlay URL
          </button>
        </div> : null}
      </div>
    </section>
  );
}
