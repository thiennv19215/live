import { Clapperboard, Gift, LayoutDashboard, Minus, RadioTower, Settings, SlidersHorizontal, Square, X, Zap } from "lucide-react";
import { useCallback, useState } from "react";
import { GiftMatrix } from "./components/GiftMatrix";
import { LogsPanel } from "./components/LogsPanel";
import { MediaLibrary } from "./components/MediaLibrary";
import { OutputStage } from "./components/OutputStage";
import { QueuePanel } from "./components/QueuePanel";
import { QuickSimulator } from "./components/QuickSimulator";
import { SettingsPanel } from "./components/SettingsPanel";
import { StatusRail } from "./components/StatusRail";
import { useBackend } from "./hooks/useBackend";

export default function App() {
  const backend = useBackend();
  const [notice, setNotice] = useState(null);
  const [activeTab, setActiveTab] = useState("live");

  const notify = useCallback((message, type = "success") => {
    setNotice({ message, type });
    window.setTimeout(() => setNotice(null), 2800);
  }, []);

  return (
    <div className="app-shell">
      <header className="titlebar">
        <div className="brand-lockup">
          <div className="brand-mark"><RadioTower size={20} /></div>
          <div><strong>TikTok Live Control Room</strong><span>React + Electron / Python Engine</span></div>
        </div>
        <StatusRail status={backend.status} online={backend.online} />
        <div className="window-actions">
          <button onClick={() => window.desktop?.minimize?.()}><Minus size={16} /></button>
          <button onClick={() => window.desktop?.toggleMaximize?.()}><Square size={13} /></button>
          <button className="close" onClick={() => window.desktop?.close?.()}><X size={16} /></button>
        </div>
      </header>

      <nav className="top-navigation">
        {[
          ["live", "Live", LayoutDashboard],
          ["stage", "Sân khấu", Clapperboard],
          ["actions", "Hành động", Zap],
          ["gifts", "Quà & lệnh", Gift],
          ["settings", "Thiết bị & cài đặt", Settings],
        ].map(([id, label, Icon]) => (
          <button className={activeTab === id ? "active" : ""} onClick={() => setActiveTab(id)} key={id}>
            <Icon size={15} /> {label}
          </button>
        ))}
      </nav>

      <main className="workspace dashboard-workspace">
        {activeTab === "live" ? (
          <div className="live-dashboard">
            <div className="live-main-column">
              <OutputStage {...backend} showLibrary={false} onNotice={notify} />
              <QueuePanel status={backend.status} post={backend.post} />
            </div>
            <aside className="live-side-column">
              <SettingsPanel {...backend} compact onNotice={notify} />
              <QuickSimulator {...backend} onNotice={notify} />
              <LogsPanel logs={backend.logs} />
            </aside>
          </div>
        ) : null}

        {activeTab === "stage" ? <div className="stage-management-grid"><MediaLibrary {...backend} onNotice={notify} /><OutputStage {...backend} showLibrary={false} onNotice={notify} /></div> : null}

        {activeTab === "actions" || activeTab === "gifts" ? (
          <div className="management-grid">
            <GiftMatrix {...backend} onNotice={notify} />
            <div className="management-side"><QuickSimulator {...backend} onNotice={notify} /><QueuePanel status={backend.status} post={backend.post} /></div>
          </div>
        ) : null}

        {activeTab === "settings" ? (
          <div className="settings-grid">
            <SettingsPanel {...backend} onNotice={notify} />
            <div className="settings-overview dashboard-card"><SlidersHorizontal size={22} /><h2>Thiết bị & hệ thống</h2><StatusRail status={backend.status} online={backend.online} /></div>
            <LogsPanel logs={backend.logs} />
          </div>
        ) : null}
      </main>

      {backend.error && !backend.online ? <div className="backend-banner">Đang chờ Python backend · {backend.error}</div> : null}
      {notice ? <div className={`toast ${notice.type}`}>{notice.message}</div> : null}
    </div>
  );
}
