import { Clapperboard, Construction, Gift, LayoutDashboard, Minus, RadioTower, Settings, SlidersHorizontal, Square, Video, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
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
  const [mediaActionId, setMediaActionId] = useState("");
  const noticeTimer = useRef(null);

  const notify = useCallback((message, type = "success") => {
    if (noticeTimer.current) window.clearTimeout(noticeTimer.current);
    setNotice({ message, type });
    noticeTimer.current = window.setTimeout(() => {
      setNotice(null);
      noticeTimer.current = null;
    }, 2800);
  }, []);

  useEffect(() => () => {
    if (noticeTimer.current) window.clearTimeout(noticeTimer.current);
  }, []);

  return (
    <div className="app-shell">
      <header className="titlebar">
        <div className="brand-lockup">
          <div className="brand-mark"><RadioTower size={20} /></div>
          <div><strong>TikTok Live Control Room</strong><span style={{ color: "#00f2fe", fontWeight: "600" }}>v1.2.0 · Audit & Thứ Tự 1-2-3</span></div>
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
          ["media", "Video hành động", Video],
          ["stage", "Sân khấu", Clapperboard, "Đang phát triển"],
          ["actions", "Tương tác TikTok", Gift],
          ["settings", "Cài đặt", Settings],
        ].map(([id, label, Icon, badge]) => (
          <button className={activeTab === id ? "active" : ""} onClick={() => setActiveTab(id)} key={id}>
            <Icon size={15} /> <span>{label}</span>{badge ? <small>{badge}</small> : null}
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

        {activeTab === "media" ? <div className="media-library-workspace"><MediaLibrary {...backend} onNotice={notify} targetActionId={mediaActionId} onTargetActionChange={setMediaActionId} /></div> : null}

        {activeTab === "stage" ? (
          <section className="stage-coming-soon">
            <div className="coming-soon-icon"><Construction size={34} /></div>
            <span>SÂN KHẤU</span>
            <h2>Đang phát triển</h2>
            <p>Khu vực dàn dựng sân khấu sẽ được mở trong phiên bản tiếp theo.</p>
          </section>
        ) : null}

        {activeTab === "actions" ? (
          <div className="automation-workspace">
            <GiftMatrix {...backend} onNotice={notify} onManageVideos={(actionId) => { setMediaActionId(actionId); setActiveTab("media"); }} />
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
      {backend.actionError ? <div className="toast error">{backend.actionError}</div> : null}
      {notice ? <div className={`toast ${notice.type}`}>{notice.message}</div> : null}
    </div>
  );
}
