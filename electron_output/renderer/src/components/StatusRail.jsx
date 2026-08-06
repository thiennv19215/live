import { Activity, Radio, Server, Wifi } from "lucide-react";

const ITEMS = [
  ["TikTok Live", "tiktok_connected", Radio],
  ["OBS WebSocket", "obs_connected", Server],
  ["Overlay nội bộ", "overlay_online", Wifi],
];

export function StatusRail({ status, online }) {
  return (
    <div className="status-rail">
      <div className={`status-item ${online ? "is-online" : ""}`}>
        <Activity size={16} />
        <span>Backend</span>
        <strong>{online ? "ONLINE" : "OFFLINE"}</strong>
      </div>
      {ITEMS.map(([label, key, Icon]) => (
        <div className={`status-item ${status[key] ? "is-online" : ""}`} key={key}>
          <Icon size={16} />
          <span>{label}</span>
          <strong>{status.mock_mode && key === "tiktok_connected" ? "SIMULATED" : status[key] ? "ONLINE" : "STANDBY"}</strong>
        </div>
      ))}
    </div>
  );
}
