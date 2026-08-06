import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

const EMPTY_STATUS = {
  running: false,
  mock_mode: false,
  tiktok_connected: false,
  obs_connected: false,
  overlay_online: false,
  overlay_url: "",
  current: null,
  queue: [],
  progress: 0,
  remaining: 0,
};

export function useBackend() {
  const [status, setStatus] = useState(EMPTY_STATUS);
  const [config, setConfig] = useState(null);
  const [mappings, setMappings] = useState([]);
  const [logs, setLogs] = useState([]);
  const [online, setOnline] = useState(false);
  const [error, setError] = useState("");
  const lastLogId = useRef(0);

  const refreshStatus = useCallback(async () => {
    try {
      const next = await api.get("/api/status");
      setStatus(next);
      setOnline(true);
      setError("");
    } catch (nextError) {
      setOnline(false);
      setError(nextError.message);
    }
  }, []);

  const refreshLogs = useCallback(async () => {
    try {
      const items = await api.get(`/api/logs?after=${lastLogId.current}`);
      if (items.length) {
        lastLogId.current = items.at(-1).id;
        setLogs((current) => [...current, ...items].slice(-160));
      }
    } catch {
      // Status polling owns the visible offline state.
    }
  }, []);

  const loadInitial = useCallback(async () => {
    try {
      const [nextConfig, nextMappings] = await Promise.all([
        api.get("/api/config"),
        api.get("/api/mappings"),
      ]);
      setConfig({
        ...nextConfig,
        mock_mode: nextConfig.mock_mode ?? true,
        enable_tiktok: nextConfig.enable_tiktok ?? false,
      });
      setMappings(nextMappings);
    } catch (nextError) {
      setError(nextError.message);
    }
  }, []);

  useEffect(() => {
    loadInitial();
    refreshStatus();
    refreshLogs();
    const timer = window.setInterval(() => {
      refreshStatus();
      refreshLogs();
    }, 800);
    return () => window.clearInterval(timer);
  }, [loadInitial, refreshLogs, refreshStatus]);

  useEffect(() => {
    if (online && (!config || mappings.length === 0)) loadInitial();
  }, [online, config, mappings.length, loadInitial]);

  const post = useCallback(async (path, body) => {
    const result = await api.post(path, body);
    await refreshStatus();
    return result;
  }, [refreshStatus]);

  return {
    status,
    config,
    setConfig,
    mappings,
    setMappings,
    logs,
    online,
    error,
    post,
    reloadConfig: loadInitial,
  };
}
