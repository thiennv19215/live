import { FolderOpen, Play, Save, Square } from "lucide-react";

const FIELDS = [
  ["tiktok_username", "TikTok username", "@username"],
  ["obs_host", "OBS host", "127.0.0.1"],
  ["obs_port", "OBS port", "4455"],
  ["obs_password", "OBS password", "••••••••", "password"],
  ["scene_name", "Scene", "Main Scene"],
];

export function SettingsPanel({ config, setConfig, status, post, onNotice, compact = false }) {
  if (!config) return compact ? null : <aside className="settings-panel loading-block">Đang tải cấu hình…</aside>;

  const update = (key, value) => setConfig((current) => ({ ...current, [key]: value }));

  const save = async () => {
    const saved = await post("/api/config", config);
    setConfig(saved);
    onNotice("Đã lưu cấu hình");
  };

  const start = async () => {
    await post("/api/system/start", {
      mock_mode: Boolean(config.mock_mode),
      enable_tiktok: Boolean(config.enable_tiktok),
      enable_obs: Boolean(config.enable_obs),
      config,
    });
    onNotice(config.mock_mode ? "Preview nội bộ đã sẵn sàng" : config.enable_obs ? "Đang kết nối TikTok và OBS" : "TikTok Studio trực tiếp đã sẵn sàng");
  };

  const selectSource = (mode) => {
    setConfig((current) => ({
      ...current,
      mock_mode: mode === "mock",
      enable_tiktok: mode === "tiktok",
    }));
  };

  const selectOutput = (mode) => {
    setConfig((current) => ({
      ...current,
      enable_obs: mode === "obs",
    }));
  };

  if (compact) {
    const sourceMode = config.mock_mode ? "mock" : config.enable_tiktok ? "tiktok" : "mock";
    return (
      <aside className="settings-panel source-card">
        <div className="source-title"><div><span>EVENT SOURCE</span><h2>Nguồn sự kiện</h2></div><i className={status.running ? "online" : ""} /></div>
        <div className="source-tabs">
          <button className={sourceMode === "tiktok" ? "active" : ""} onClick={() => selectSource("tiktok")}>TikTok trực tiếp</button>
          <button disabled title="Sắp hỗ trợ">TikFinity</button>
          <button className={sourceMode === "mock" ? "active" : ""} onClick={() => selectSource("mock")}>Giả lập</button>
        </div>
        <p>{sourceMode === "mock" ? "Phát thử video và audio trực tiếp trong preview, không cần OBS." : "Nhận quà TikTok realtime và điều khiển luồng phát."}</p>
        <div className="source-title"><div><span>PLAYBACK OUTPUT</span><h2>Đầu ra phát video</h2></div></div>
        <div className="source-tabs output-tabs">
          <button className={!config.enable_obs ? "active" : ""} onClick={() => selectOutput("app")}>Output của app</button>
          <button className={config.enable_obs ? "active" : ""} onClick={() => selectOutput("obs")}>OBS</button>
        </div>
        <p>{config.enable_obs ? "Phát đồng thời qua OBS và Output của app." : "Chỉ phát trực tiếp trong Preview/Output của app; không kết nối OBS."}</p>
        <div className="source-actions">
          <button className="primary-action" onClick={start} disabled={status.running}><Play size={15} fill="currentColor" /> {sourceMode === "mock" ? "Bật giả lập" : "Kết nối TikTok"}</button>
          <button className="stop-action" onClick={() => post("/api/system/stop")} disabled={!status.running}><Square size={13} fill="currentColor" /> Ngắt</button>
        </div>
      </aside>
    );
  }

  return (
    <aside className="settings-panel">
      <div className="panel-heading">
        <div>
          <span>{compact ? "EVENT SOURCE" : "CONTROL INPUT"}</span>
          <h2>{compact ? "Nguồn sự kiện" : "Cấu hình phiên live"}</h2>
        </div>
        <button className="icon-button" onClick={save} title="Lưu cấu hình"><Save size={17} /></button>
      </div>

      <div className="system-actions">
        <button className="primary-action" onClick={start} disabled={status.running}>
          <Play size={17} fill="currentColor" /> Bắt đầu kết nối
        </button>
        <button className="stop-action" onClick={() => post("/api/system/stop")} disabled={!status.running}>
          <Square size={15} fill="currentColor" /> Dừng
        </button>
      </div>

      <div className="toggle-row">
        <label><input type="checkbox" checked={Boolean(config.mock_mode)} onChange={(event) => update("mock_mode", event.target.checked)} /> Preview nội bộ</label>
        <label><input type="checkbox" checked={Boolean(config.enable_tiktok)} onChange={(event) => update("enable_tiktok", event.target.checked)} /> TikTok realtime</label>
        <label><input type="checkbox" checked={Boolean(config.enable_obs)} onChange={(event) => update("enable_obs", event.target.checked)} /> Đồng bộ OBS</label>
      </div>

      {!compact ? <div className="form-stack">
        {FIELDS.map(([key, label, placeholder, type = "text"]) => (
          <label className="field" key={key}>
            <span>{label}</span>
            <input
              type={type}
              value={config[key] ?? ""}
              placeholder={placeholder}
              onChange={(event) => update(key, key === "obs_port" ? Number(event.target.value) : event.target.value)}
            />
          </label>
        ))}
      </div> : null}

      {!compact ? <button className="folder-button" onClick={() => window.desktop?.openVideosFolder?.()}>
        <FolderOpen size={16} /> Mở thư mục videos
      </button> : null}
    </aside>
  );
}
