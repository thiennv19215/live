import { Minus, RadioTower, Square, X } from "lucide-react";
import { useCallback, useState } from "react";
import { GiftMatrix } from "./components/GiftMatrix";
import { LogsPanel } from "./components/LogsPanel";
import { OutputStage } from "./components/OutputStage";
import { QueuePanel } from "./components/QueuePanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { StatusRail } from "./components/StatusRail";
import { useBackend } from "./hooks/useBackend";

export default function App() {
  const backend = useBackend();
  const [notice, setNotice] = useState(null);

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

      <main className="workspace">
        <SettingsPanel {...backend} onNotice={notify} />
        <div className="center-column">
          <OutputStage {...backend} onNotice={notify} />
          <LogsPanel logs={backend.logs} />
        </div>
        <div className="right-column">
          <GiftMatrix {...backend} onNotice={notify} />
          <QueuePanel status={backend.status} post={backend.post} />
        </div>
      </main>

      {backend.error && !backend.online ? <div className="backend-banner">Đang chờ Python backend · {backend.error}</div> : null}
      {notice ? <div className={`toast ${notice.type}`}>{notice.message}</div> : null}
    </div>
  );
}
