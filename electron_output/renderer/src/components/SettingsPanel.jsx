import { FolderOpen, Play, Save, Square, Video } from "lucide-react";

const FIELDS = [
  ["tiktok_username", "TikTok username", "@username"],
  ["obs_host", "OBS host", "127.0.0.1"],
  ["obs_port", "OBS port", "4455"],
  ["obs_password", "OBS password", "••••••••", "password"],
  ["scene_name", "Scene", "Main Scene"],
];

export function SettingsPanel({ config, setConfig, status, post, onNotice }) {
  if (!config) return <aside className="settings-panel loading-block">Đang tải cấu hình…</aside>;

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
      config,
    });
    onNotice(config.mock_mode ? "Đã chạy chế độ giả lập" : "Đang kết nối hệ thống");
  };

  const pickIdle = async () => {
    const path = await window.desktop?.pickMedia?.();
    if (!path) return;
    await post("/api/media/idle", { path });
    setConfig((current) => ({ ...current, idle_video_path: path }));
    onNotice("Đã thay video nền");
  };

  return (
    <aside className="settings-panel">
      <div className="panel-heading">
        <div>
          <span>CONTROL INPUT</span>
          <h2>Cấu hình phiên live</h2>
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
        <label><input type="checkbox" checked={Boolean(config.mock_mode)} onChange={(event) => update("mock_mode", event.target.checked)} /> Giả lập</label>
        <label><input type="checkbox" checked={Boolean(config.enable_tiktok)} onChange={(event) => update("enable_tiktok", event.target.checked)} /> TikTok realtime</label>
      </div>

      <div className="form-stack">
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
      </div>

      <div className="media-picker">
        <div className="media-icon"><Video size={20} /></div>
        <div className="media-copy">
          <span>Video nền đang dùng</span>
          <strong title={config.idle_video_path}>{config.idle_video_path?.split(/[\\/]/).at(-1) || "Chưa chọn video"}</strong>
        </div>
        <button className="icon-button" onClick={pickIdle} title="Chọn media"><FolderOpen size={17} /></button>
      </div>

      <button className="folder-button" onClick={() => window.desktop?.openVideosFolder?.()}>
        <FolderOpen size={16} /> Mở thư mục videos
      </button>
    </aside>
  );
}
