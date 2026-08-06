import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

const EMPTY_STATUS = {
  running: false,
  mock_mode: false,
  tiktok_connected: false,
  obs_connected: false,
  obs_enabled: false,
  overlay_online: false,
  overlay_url: "",
  current: null,
  queue: [],
  playback_state: "idle",
  queue_pending: 0,
  queue_total: 0,
  progress: 0,
  remaining: 0,
};

export function useBackend() {
  const [status, setStatus] = useState(EMPTY_STATUS);
  const [config, setConfig] = useState(null);
  const [mappings, setMappings] = useState([]);
  const [actions, setActions] = useState([]);
  const [logs, setLogs] = useState([]);
  const [online, setOnline] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const lastLogId = useRef(0);
  const statusInFlight = useRef(false);
  const logsInFlight = useRef(false);

  const refreshStatus = useCallback(async () => {
    if (statusInFlight.current) return;
    statusInFlight.current = true;
    try {
      const next = await api.get("/api/status");
      setStatus(next);
      setOnline(true);
      setError("");
    } catch (nextError) {
      setOnline(false);
      setError(nextError.message);
    } finally {
      statusInFlight.current = false;
    }
  }, []);

  const refreshLogs = useCallback(async () => {
    if (logsInFlight.current) return;
    logsInFlight.current = true;
    try {
      const items = await api.get(`/api/logs?after=${lastLogId.current}`);
      if (items.length) {
        lastLogId.current = items.at(-1).id;
        setLogs((current) => [...current, ...items].slice(-160));
      }
    } catch {
      // Status polling owns the visible offline state.
    } finally {
      logsInFlight.current = false;
    }
  }, []);

  const loadInitial = useCallback(async () => {
    try {
      const [nextConfig, nextMappings, nextActions] = await Promise.all([
        api.get("/api/config"),
        api.get("/api/mappings"),
        api.get("/api/actions"),
      ]);
      setConfig({
        ...nextConfig,
        mock_mode: nextConfig.mock_mode ?? true,
        enable_tiktok: nextConfig.enable_tiktok ?? false,
        enable_obs: nextConfig.enable_obs ?? false,
      });
      setMappings(nextMappings);
      setActions(nextActions);
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
    try {
      const result = await api.post(path, body);
      setActionError("");
      await refreshStatus();
      return result;
    } catch (nextError) {
      setActionError(nextError.message);
      throw nextError;
    }
  }, [refreshStatus]);

  return {
    status,
    config,
    setConfig,
    mappings,
    setMappings,
    actions,
    setActions,
    logs,
    online,
    error,
    actionError,
    post,
    reloadConfig: loadInitial,
  };
}
