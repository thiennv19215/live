"""Local browser overlay output for TikTok Live Studio."""

from __future__ import annotations

import contextlib
import hashlib
import json
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from websockets.exceptions import ConnectionClosed
from websockets.sync.server import serve as serve_websocket


IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}


OVERLAY_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <title>TikTok Live Overlay</title>
  <style>
    :root { color-scheme: dark; background: #000; }
    * { box-sizing: border-box; }
    html, body, main { width: 100%; height: 100%; margin: 0; overflow: hidden; background: #000; }
    main { position: relative; isolation: isolate; }
    .media {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: var(--media-fit, cover);
      object-position: center;
      background: transparent;
      opacity: 0;
      transform: scale(var(--media-zoom, 1)) translateZ(0);
      will-change: opacity, transform;
      backface-visibility: hidden;
      /* Idle is kept alive under the action, so this is a real cross-fade
         instead of exposing a black frame while media is swapped. */
      transition: opacity 220ms cubic-bezier(.22, .61, .36, 1);
    }
    .media.active { opacity: 1; }
    .media.no-transition { transition: none !important; }
    #status {
      position: absolute;
      left: 50%;
      top: 4vh;
      z-index: 10;
      max-width: 90%;
      transform: translateX(-50%) translateY(-20px) scale(0.95);
      padding: 14px 28px;
      border: 1.5px solid rgba(255, 0, 127, 0.5);
      border-radius: 50px;
      background: linear-gradient(135deg, rgba(25, 10, 40, 0.88), rgba(10, 25, 50, 0.88));
      box-shadow: 0 10px 35px rgba(0, 0, 0, 0.65), 0 0 22px rgba(255, 0, 127, 0.35);
      color: #ffffff;
      font: 700 clamp(16px, 2.2vw, 32px)/1.3 "Segoe UI", system-ui, sans-serif;
      letter-spacing: .02em;
      text-align: center;
      backdrop-filter: blur(16px);
      opacity: 0;
      pointer-events: none;
      transition: all 350ms cubic-bezier(0.34, 1.56, 0.64, 1);
    }
    #status.visible {
      opacity: 1;
      transform: translateX(-50%) translateY(0) scale(1);
    }
    #gift-guide {
      position: absolute;
      left: 4%;
      top: 20%;
      z-index: 9;
      display: none;
      width: clamp(190px, 23vw, 360px);
      border: 1px solid rgba(186, 162, 255, .72);
      border-radius: clamp(12px, 1.4vw, 20px);
      background: transparent;
      box-shadow: 0 0 20px rgba(107, 67, 209, .28);
      color: #fff;
      font-family: "Segoe UI", system-ui, sans-serif;
      overflow: hidden;
      touch-action: none;
      -webkit-app-region: no-drag;
    }
    #gift-guide.visible { display: block; }
    #gift-guide.dragging { cursor: grabbing; box-shadow: 0 0 0 2px rgba(210, 190, 255, .85), 0 0 30px rgba(107, 67, 209, .52); }
    .gift-guide-intro { display: none; }
    .gift-guide-list { display: grid; gap: clamp(5px, .7vw, 9px); padding: clamp(12px, 1.4vw, 18px) clamp(11px, 1.2vw, 16px); }
    .gift-guide-item { display: grid; grid-template-columns: clamp(24px, 2.5vw, 38px) minmax(0, 1fr); align-items: center; gap: 9px; min-width: 0; }
    .gift-guide-item b, .gift-guide-item span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .gift-guide-item b { color: #f7f5ff; font-size: clamp(10px, 1.15vw, 16px); text-shadow: 0 2px 7px #000; }
    .gift-guide-item span { margin-top: 2px; color: #d4c9ff; font-size: clamp(8px, .9vw, 13px); font-weight: 700; text-shadow: 0 2px 7px #000; }
    .gift-guide-icon { display: grid; width: clamp(24px, 2.5vw, 38px); height: clamp(24px, 2.5vw, 38px); place-items: center; border-radius: 9px; background: rgba(141, 112, 239, .12); font-size: clamp(16px, 1.8vw, 26px); }
    .gift-guide-footer { margin-top: 2px; padding: clamp(8px, 1vw, 13px) clamp(13px, 1.5vw, 20px); border-top: 1px solid rgba(166, 137, 255, .33); color: #e4dcff; font-size: clamp(8px, .9vw, 13px); font-weight: 800; letter-spacing: .04em; text-shadow: 0 2px 7px #000; }
    .gift-guide-footer[hidden] { display: none; }
  </style>
</head>
<body>
  <main>
    <video id="video-idle" class="media" autoplay playsinline preload="auto"></video>
    <video id="video-action-a" class="media" autoplay playsinline preload="auto"></video>
    <video id="video-action-b" class="media" autoplay playsinline preload="auto"></video>
    <img id="image-a" class="media" alt="">
    <img id="image-b" class="media" alt="">
    <audio id="background-music" loop preload="auto"></audio>
    <audio id="sound" preload="auto"></audio>
    <div id="status">Waiting for media</div>
    <aside id="gift-guide" aria-label="Danh sách quà và hiệu ứng">
      <div class="gift-guide-list" id="gift-guide-items"></div>
      <div class="gift-guide-footer" id="gift-guide-footer"></div>
    </aside>
  </main>
  <script>
    const query = new URLSearchParams(location.search);
    const debug = query.get("debug") === "1";
    const muted = query.get("muted") === "1";
    const mediaFit = query.get("fit") === "contain" ? "contain" : "cover";
    const requestedZoom = Number.parseFloat(query.get("zoom") || "1");
    const mediaZoom = Number.isFinite(requestedZoom) ? Math.min(1.3, Math.max(1, requestedZoom)) : 1;
    const giftGuideEnabled = query.get("gift_guide") === "1";
    const configApiUrl = query.get("config_api") || "http://127.0.0.1:8766/api/config";
    document.documentElement.style.setProperty("--media-fit", mediaFit);
    document.documentElement.style.setProperty("--media-zoom", String(mediaZoom));
    const idleVideo = document.querySelector("#video-idle");
    const actionVideos = [document.querySelector("#video-action-a"), document.querySelector("#video-action-b")];
    const videos = [idleVideo, ...actionVideos];
    const images = [document.querySelector("#image-a"), document.querySelector("#image-b")];
    const backgroundMusic = document.querySelector("#background-music");
    const sound = document.querySelector("#sound");
    const status = document.querySelector("#status");
    const giftGuide = document.querySelector("#gift-guide");
    const giftGuideItems = document.querySelector("#gift-guide-items");
    const giftGuideFooter = document.querySelector("#gift-guide-footer");
    const position = { x: Number(query.get("gift_x") || 4), y: Number(query.get("gift_y") || 20) };
    const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));
    giftGuide.style.left = `${clamp(position.x, 0, 95)}%`;
    giftGuide.style.top = `${clamp(position.y, 0, 92)}%`;
    let configuredGifts = [];
    try { configuredGifts = JSON.parse(query.get("gift_items") || "[]"); } catch {}
    if (!Array.isArray(configuredGifts)) configuredGifts = [];
    configuredGifts.slice(0, 8).forEach((item) => {
      const row = document.createElement("div");
      row.className = "gift-guide-item";
      const icon = document.createElement("i");
      icon.className = "gift-guide-icon";
      icon.textContent = item.icon || "🎁";
      const copy = document.createElement("div");
      const name = document.createElement("b");
      name.textContent = item.gift || "Quà tặng";
      const action = document.createElement("span");
      action.textContent = item.action || "Kích hoạt hiệu ứng";
      copy.append(name, action);
      row.append(icon, copy);
      giftGuideItems.append(row);
    });
    giftGuideFooter.textContent = query.get("gift_footer") || "";
    giftGuideFooter.hidden = !giftGuideFooter.textContent;
    giftGuide.classList.toggle("visible", giftGuideEnabled);
    let dragState = null;
    function saveGiftGuidePosition() {
      const nextPosition = { x: Number.parseFloat(giftGuide.style.left), y: Number.parseFloat(giftGuide.style.top) };
      window.parent?.postMessage({ type: "gift-layout-position", position: nextPosition }, "*");
      fetch(configApiUrl, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ gift_panel_position: nextPosition }) }).catch(() => {});
    }
    giftGuide.addEventListener("pointerdown", (event) => {
      if (!giftGuideEnabled || event.button !== 0) return;
      const bounds = giftGuide.getBoundingClientRect();
      dragState = { offsetX: event.clientX - bounds.left, offsetY: event.clientY - bounds.top };
      giftGuide.classList.add("dragging");
      giftGuide.setPointerCapture(event.pointerId);
      event.preventDefault();
    });
    giftGuide.addEventListener("pointermove", (event) => {
      if (!dragState) return;
      const bounds = giftGuide.getBoundingClientRect();
      const x = clamp(((event.clientX - dragState.offsetX) / window.innerWidth) * 100, 0, 100 - (bounds.width / window.innerWidth) * 100);
      const y = clamp(((event.clientY - dragState.offsetY) / window.innerHeight) * 100, 0, 100 - (bounds.height / window.innerHeight) * 100);
      giftGuide.style.left = `${x.toFixed(2)}%`;
      giftGuide.style.top = `${y.toFixed(2)}%`;
    });
    giftGuide.addEventListener("pointerup", (event) => {
      if (!dragState) return;
      dragState = null;
      giftGuide.classList.remove("dragging");
      giftGuide.releasePointerCapture(event.pointerId);
      saveGiftGuidePosition();
    });
    let currentVersion = -1;
    let currentBackgroundMusicVersion = -1;
    let currentMediaAudioVersion = -1;
    let activeMedia = null;
    let loadGeneration = 0;
    let socket = null;
    let reconnectTimer = null;

    async function syncBackgroundMusic(state) {
      const nextBackgroundMusicVersion = Number(state.background_music_version || 0);
      const mediaUrl = state.background_music_url || "";
      if (!mediaUrl) {
        backgroundMusic.pause();
        backgroundMusic.removeAttribute("src");
        delete backgroundMusic.dataset.mediaUrl;
        currentBackgroundMusicVersion = nextBackgroundMusicVersion;
        return;
      }
      syncBackgroundMusicMute(state);
      if (backgroundMusic.dataset.mediaUrl !== mediaUrl) {
        backgroundMusic.pause();
        backgroundMusic.dataset.mediaUrl = mediaUrl;
        backgroundMusic.src = mediaUrl;
        backgroundMusic.load();
        if (backgroundMusic.readyState < 1) await waitForReady(backgroundMusic, "loadedmetadata");
        const startedAt = Number(state.background_music_started_at_ms);
        if (Number.isFinite(startedAt) && Number.isFinite(backgroundMusic.duration) && backgroundMusic.duration > 0) {
          backgroundMusic.currentTime = Math.max(0, (Date.now() - startedAt) / 1000) % backgroundMusic.duration;
        }
      }
      try {
        await backgroundMusic.play();
      } catch (error) {
        if (debug) showStatus(`Background audio blocked: ${error.message}`, true);
      }
      currentBackgroundMusicVersion = nextBackgroundMusicVersion;
    }

    function syncBackgroundMusicMute(state) {
      backgroundMusic.muted = muted || Boolean(state.background_music_muted) || state.mode === "action";
    }

    function syncMediaAudio(state) {
      currentMediaAudioVersion = Number(state.media_audio_version || 0);
      idleVideo.dataset.targetMuted = String(muted || Boolean(state.idle_video_muted));
      if (activeMedia === idleVideo) idleVideo.muted = idleVideo.dataset.targetMuted === "true";
    }

    function sendPlaybackEvent(type, state, detail = "") {
      if (socket?.readyState !== WebSocket.OPEN) return;
      socket.send(JSON.stringify({ type, playback_id: state.version, mode: state.mode, detail }));
    }

    function showStatus(text, force = false) {
      status.textContent = text;
      status.classList.toggle("visible", force || debug);
    }

    function releaseMedia(element) {
      if (!element) return;
      element.classList.remove("active");
      element.classList.remove("no-transition");
      element.onended = null;
      if (element.tagName === "VIDEO") element.pause();
      element.removeAttribute("src");
      delete element.dataset.mode;
      delete element.dataset.mediaUrl;
      if (element.tagName === "VIDEO") element.load();
    }

    function hideActionImmediately(element) {
      if (!element) return;
      // The decoder may expose a black terminal frame immediately before
      // `ended`. Never fade that frame over the live Idle layer.
      element.classList.add("no-transition");
      element.classList.remove("active");
      requestAnimationFrame(() => requestAnimationFrame(() => {
        element.classList.remove("no-transition");
      }));
    }

    function hideMedia() {
      [...videos, ...images].forEach(releaseMedia);
      activeMedia = null;
      sound.pause();
      sound.removeAttribute("src");
    }

    function waitForReady(element, eventName) {
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error("Media load timed out")), 8000);
        const cleanup = () => {
          clearTimeout(timeout);
          element.removeEventListener(eventName, ready);
          element.removeEventListener("error", failed);
        };
        const ready = () => { cleanup(); resolve(); };
        const failed = () => { cleanup(); reject(new Error("Media could not be decoded")); };
        element.addEventListener(eventName, ready, { once: true });
        element.addEventListener("error", failed, { once: true });
      });
    }

    function syncToSharedClock(video, state) {
      const startedAt = Number(state.started_at_ms);
      if (!Number.isFinite(startedAt) || !Number.isFinite(video.duration) || video.duration <= 0) return;
      const elapsed = Math.max(0, (Date.now() - startedAt) / 1000);
      const target = state.mode === "idle"
        ? elapsed % video.duration
        : Math.min(elapsed, Math.max(0, video.duration - 0.04));
      // Synchronize only while preparing a newly-loaded element. Re-seeking a
      // playing Chromium/OBS video on every state poll causes visible freezes.
      if (Math.abs(video.currentTime - target) > 0.5) video.currentTime = target;
    }

    async function prepareMedia(state, mediaUrl) {
      const pool = state.media_type === "image"
        ? images
        : state.mode === "idle" ? [idleVideo] : actionVideos;
      const cached = pool.find((element) => element.dataset.mediaUrl === mediaUrl && element.getAttribute("src"));
      if (cached) {
        cached.dataset.mode = state.mode;
        if (cached.tagName === "VIDEO") {
          // Idle kept playing behind the action, so revealing it must not seek.
          if (state.mode === "action") cached.currentTime = 0;
          await cached.play();
          sendPlaybackEvent("media_ready", state);
        }
        return cached;
      }
      const next = pool.find((element) => element !== activeMedia) || pool[0];
      releaseMedia(next);
      next.style.zIndex = "2";
      next.dataset.mode = state.mode;
      next.dataset.mediaUrl = mediaUrl;

      if (state.media_type === "image") {
        next.src = mediaUrl;
        if (!next.complete) await waitForReady(next, "load");
        if (next.decode) await next.decode().catch(() => {});
      } else {
        next.loop = state.mode === "idle";
        next.muted = true;
        next.dataset.targetMuted = String(muted || Boolean(state.sound_url) || Boolean(state.media_muted));
        next.src = mediaUrl;
        next.load();
        if (next.readyState < 3) await waitForReady(next, "canplay");
        syncToSharedClock(next, state);
        await next.play();
        sendPlaybackEvent("media_ready", state);
        next.onended = state.mode === "action" ? () => {
          // Reveal the already-running idle layer immediately. Waiting for the
          // next poll here can expose the action video's black final frame.
          hideActionImmediately(next);
          sound.pause();
          sendPlaybackEvent("media_ended", state);
        } : null;
      }
      return next;
    }

    function preloadNextAction(mediaUrl) {
      if (!mediaUrl) return;
      const alreadyLoaded = actionVideos.find((video) => video.dataset.mediaUrl === mediaUrl && video.getAttribute("src"));
      if (alreadyLoaded) return;
      const target = actionVideos.find((video) => video !== activeMedia) || actionVideos[0];
      releaseMedia(target);
      target.dataset.mode = "action";
      target.dataset.mediaUrl = mediaUrl;
      target.muted = true;
      target.preload = "auto";
      target.src = mediaUrl;
      target.load();
    }

    async function swapMedia(next) {
      const previous = activeMedia;
      videos.forEach((video) => {
        if (video !== next) video.muted = true;
      });
      if (previous) previous.style.zIndex = "1";
      next.style.zIndex = "2";
      next.classList.add("active");
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      activeMedia = next;
      if (next.tagName === "VIDEO") next.muted = next.dataset.targetMuted === "true";
      if (previous && previous !== next) {
        const keepIdleBehindAction = previous.dataset.mode === "idle" && next.dataset.mode === "action";
        if (!keepIdleBehindAction) {
          const returningToIdle = previous.dataset.mode === "action" && next.dataset.mode === "idle";
          if (returningToIdle) hideActionImmediately(previous);
          else previous.classList.remove("active");
          const retiredMediaUrl = previous.dataset.mediaUrl;
          setTimeout(() => {
            // Don't clear this element if it was already reused to preload the
            // next queued action during the transition delay.
            if (previous !== activeMedia && previous.dataset.mediaUrl === retiredMediaUrl) releaseMedia(previous);
          }, 250);
        }
      }
    }

    async function applyState(state) {
      if (state.version === currentVersion) return;
      currentVersion = state.version;
      const generation = ++loadGeneration;
      showStatus(`${state.mode.toUpperCase()} - ${state.label || "No media"}`, !state.media_url);
      if (!state.media_url) {
        hideMedia();
        return;
      }

      // media_url is fingerprinted by file contents/metadata. Keep it stable
      // across playbacks so Chromium can reuse its memory/disk media cache.
      const mediaUrl = state.media_url;
      try {
        const next = await prepareMedia(state, mediaUrl);
        if (generation !== loadGeneration) {
          releaseMedia(next);
          return;
        }
        await swapMedia(next);
        preloadNextAction(state.next_media_url);
      } catch (error) {
        // A newer idle/action state can pause this element while its play()
        // promise is still pending.  That is an expected transition, not a
        // playback failure worth showing to the audience.
        if (generation !== loadGeneration || error?.name === "AbortError") return;
        sendPlaybackEvent("media_error", state, error.message);
        showStatus(`Playback failed: ${error.message}`, true);
        return;
      }

      sound.pause();
      if (state.sound_url && !muted) {
        sound.src = state.sound_url;
        try {
          if (sound.readyState < 1) await waitForReady(sound, "loadedmetadata");
          syncToSharedClock(sound, state);
          await sound.play();
        } catch (error) { if (debug) showStatus(`Audio blocked: ${error.message}`, true); }
      }
    }

    function connectSocket() {
      clearTimeout(reconnectTimer);
      const protocol = location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${protocol}//${location.hostname}:__WS_PORT__`);
      socket.onopen = () => showStatus("Output connected");
      socket.onmessage = async (event) => {
        try {
          const message = JSON.parse(event.data);
          const state = message.state || message;
          if (message.type && message.type !== "playback_state") return;
          if (Number(state.background_music_version || 0) !== currentBackgroundMusicVersion) {
            await syncBackgroundMusic(state);
          }
          if (state.mode === "action") syncBackgroundMusicMute(state);
          if (Number(state.media_audio_version || 0) !== currentMediaAudioVersion) {
            syncMediaAudio(state);
          }
          if (state.version !== currentVersion) await applyState(state);
          // Only restore background audio after the idle layer is active and
          // action video/sound teardown has completed.
          if (state.mode !== "idle" || activeMedia?.dataset.mode === "idle") {
            syncBackgroundMusicMute(state);
          }
        } catch (error) {
          showStatus(`Invalid playback state: ${error.message}`, true);
        }
      };
      socket.onerror = () => socket.close();
      socket.onclose = () => {
        showStatus("Output disconnected; reconnecting…", true);
        reconnectTimer = setTimeout(connectSocket, 500);
      };
    }

    connectSocket();
  </script>
</body>
</html>
"""


class OverlayState:
    def __init__(self, idle_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._idle_path = Path(idle_path).resolve() if idle_path else None
        self._action_path: Path | None = None
        self._next_action_path: Path | None = None
        self._sound_path: Path | None = None
        self._background_music_path: Path | None = None
        self._background_music_muted = False
        self._background_music_version = 0
        self._idle_video_muted = False
        self._media_audio_version = 0
        self._mode = "idle"
        self._label = self._idle_path.name if self._idle_path else "No idle media"
        self._version = 1
        self._assets: dict[str, Path] = {}
        self._idle_started_at_ms = int(time.time() * 1000)
        self._started_at_ms = self._idle_started_at_ms
        self._background_music_started_at_ms = self._idle_started_at_ms

    def _register_asset(self, path: Path, kind: str) -> str:
        stat = path.stat()
        identity = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
        fingerprint = hashlib.sha256(identity).hexdigest()[:20]
        route = f"/{kind}/{fingerprint}{path.suffix.lower()}"
        self._assets[route] = path.resolve()
        if len(self._assets) > 200:
            oldest = next(iter(self._assets))
            self._assets.pop(oldest, None)
        return route

    def resolve_asset(self, route: str) -> Path | None:
        with self._lock:
            path = self._assets.get(route)
            return path if path and path.is_file() else None

    def set_idle_path(self, path: Path | None) -> None:
        resolved = Path(path).resolve() if path else None
        with self._lock:
            self._idle_path = resolved
            self._idle_started_at_ms = int(time.time() * 1000)
            if self._mode == "idle":
                self._label = resolved.name if resolved else "No idle media"
                self._version += 1
                self._started_at_ms = self._idle_started_at_ms

    def set_background_music(self, path: Path | None, muted: bool = False) -> None:
        resolved = Path(path).resolve() if path else None
        with self._lock:
            path_changed = resolved != self._background_music_path
            muted_changed = bool(muted) != self._background_music_muted
            if not path_changed and not muted_changed:
                return
            self._background_music_path = resolved
            self._background_music_muted = bool(muted)
            if path_changed:
                self._background_music_started_at_ms = int(time.time() * 1000)
            self._background_music_version += 1

    def set_idle_video_muted(self, muted: bool) -> None:
        with self._lock:
            next_muted = bool(muted)
            if next_muted == self._idle_video_muted:
                return
            self._idle_video_muted = next_muted
            self._media_audio_version += 1

    def show_action(
        self,
        path: Path,
        sound_path: Path | None = None,
        label: str = "",
        preload_path: Path | None = None,
    ) -> None:
        with self._lock:
            self._action_path = Path(path).resolve()
            self._sound_path = Path(sound_path).resolve() if sound_path else None
            self._next_action_path = Path(preload_path).resolve() if preload_path else None
            self._mode = "action"
            self._label = label or self._action_path.name
            self._version += 1
            self._started_at_ms = int(time.time() * 1000)

    def show_idle(self, preload_path: Path | None = None) -> None:
        with self._lock:
            self._action_path = None
            self._sound_path = None
            self._next_action_path = Path(preload_path).resolve() if preload_path else None
            self._mode = "idle"
            self._label = self._idle_path.name if self._idle_path else "No idle media"
            self._version += 1
            # The idle element remains alive underneath actions. Preserve its
            # original clock so returning to idle never jumps back to frame 0.
            self._started_at_ms = self._idle_started_at_ms

    def snapshot(self) -> tuple[dict[str, object], Path | None, Path | None]:
        with self._lock:
            media_path = self._action_path if self._mode == "action" else self._idle_path
            sound_path = self._sound_path if self._mode == "action" else None
            media_exists = bool(media_path and media_path.is_file())
            sound_exists = bool(sound_path and sound_path.is_file())
            background_music_exists = bool(self._background_music_path and self._background_music_path.is_file())
            next_exists = bool(self._next_action_path and self._next_action_path.is_file())
            media_url = self._register_asset(media_path, "media") if media_exists and media_path else ""
            sound_url = self._register_asset(sound_path, "audio") if sound_exists and sound_path else ""
            background_music_url = self._register_asset(self._background_music_path, "audio") if background_music_exists and self._background_music_path else ""
            next_media_url = self._register_asset(self._next_action_path, "media") if next_exists and self._next_action_path else ""
            payload: dict[str, object] = {
                "mode": self._mode if media_exists else "empty",
                "label": self._label,
                "version": self._version,
                "started_at_ms": self._started_at_ms,
                "media_type": "image" if media_path and media_path.suffix.lower() in IMAGE_EXTENSIONS else "video",
                "media_muted": self._idle_video_muted if self._mode == "idle" else False,
                "idle_video_muted": self._idle_video_muted,
                "media_audio_version": self._media_audio_version,
                "media_url": media_url,
                "sound_url": sound_url,
                "background_music_url": background_music_url,
                "background_music_muted": self._background_music_muted,
                "background_music_version": self._background_music_version,
                "background_music_started_at_ms": self._background_music_started_at_ms,
                "next_media_url": next_media_url,
            }
            return payload, media_path if media_exists else None, sound_path if sound_exists else None


class _OverlayHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    # Windows SO_REUSEADDR can route one port to multiple processes unpredictably.
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], overlay: "LocalOverlayServer") -> None:
        self.overlay = overlay
        super().__init__(address, _OverlayRequestHandler)


class _OverlayRequestHandler(BaseHTTPRequestHandler):
    server: _OverlayHttpServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_HEAD(self) -> None:
        self._handle_request(send_body=False)

    def do_GET(self) -> None:
        self._handle_request(send_body=True)

    def _handle_request(self, send_body: bool) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/overlay"):
            self._send_bytes(self.server.overlay.render_html().encode("utf-8"), "text/html; charset=utf-8", send_body, no_store=True)
            return
        if path == "/health":
            self._send_bytes(b"ok", "text/plain; charset=utf-8", send_body)
            return
        payload, _, _ = self.server.overlay.state.snapshot()
        if path == "/api/state":
            self._send_bytes(json.dumps(payload).encode("utf-8"), "application/json", send_body, no_store=True)
            return
        asset_path = self.server.overlay.state.resolve_asset(path)
        if asset_path and (path.startswith("/media/") or path.startswith("/audio/")):
            self._send_file(asset_path, send_body)
            return
        self.send_error(404)

    def _send_bytes(self, data: bytes, content_type: str, send_body: bool, no_store: bool = False) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if no_store:
            self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        if send_body:
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                # Chromium cancels in-flight preview requests when Output opens.
                pass

    def _send_file(self, path: Path, send_body: bool) -> None:
        size = path.stat().st_size
        start, end = 0, max(size - 1, 0)
        status = 200
        range_header = self.headers.get("Range", "")
        if range_header.startswith("bytes="):
            try:
                raw_start, raw_end = range_header[6:].split("-", 1)
                if raw_start:
                    start = int(raw_start)
                    end = int(raw_end) if raw_end else size - 1
                elif raw_end:
                    # A suffix range (bytes=-N) requests the final N bytes.
                    # Chromium uses this to read MP4 metadata stored at EOF.
                    suffix_length = int(raw_end)
                    start = max(size - suffix_length, 0)
                    end = size - 1
                else:
                    raise ValueError("empty byte range")
                if start < 0 or start >= size or end < start:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                end = min(end, size - 1)
                status = 206
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        length = max(end - start + 1, 0)
        self.send_response(status)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if not send_body or length <= 0:
            return
        with path.open("rb") as source:
            source.seek(start)
            remaining = length
            while remaining > 0:
                chunk = source.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                    # A hidden/unmounted preview is an expected disconnect.
                    break
                remaining -= len(chunk)


class LocalOverlayServer:
    def __init__(self, idle_path: Path | None = None, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self.state = OverlayState(idle_path)
        self._server: _OverlayHttpServer | None = None
        self._thread: threading.Thread | None = None
        self.ws_port = 0
        self._ws_server: object | None = None
        self._ws_thread: threading.Thread | None = None
        self._ws_clients: set[object] = set()
        self._ws_lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/overlay"

    def start(self) -> str:
        if self.is_running:
            return self.url
        last_error: OSError | None = None
        candidate_ports = [self.port] if self.port == 0 else list(range(self.port, self.port + 10))
        for candidate in candidate_ports:
            try:
                self._server = _OverlayHttpServer((self.host, candidate), self)
                self.port = int(self._server.server_address[1])
                break
            except OSError as exc:
                last_error = exc
        if self._server is None:
            raise last_error or OSError("No local port available for overlay")
        self._thread = threading.Thread(target=self._server.serve_forever, name="tiktok-overlay", daemon=True)
        self._thread.start()
        self._start_websocket()
        return self.url

    def render_html(self) -> str:
        return OVERLAY_HTML.replace("__WS_PORT__", str(self.ws_port))

    def _start_websocket(self) -> None:
        last_error: OSError | None = None
        for candidate in range(self.port + 100, self.port + 110):
            try:
                self._ws_server = serve_websocket(self._handle_websocket, self.host, candidate)
                self.ws_port = candidate
                break
            except OSError as exc:
                last_error = exc
        if self._ws_server is None:
            raise last_error or OSError("No local port available for overlay WebSocket")
        self._ws_thread = threading.Thread(
            target=self._ws_server.serve_forever,
            name="tiktok-overlay-websocket",
            daemon=True,
        )
        self._ws_thread.start()

    def _handle_websocket(self, connection: object) -> None:
        with self._ws_lock:
            self._ws_clients.add(connection)
        try:
            payload, _, _ = self.state.snapshot()
            connection.send(json.dumps({"type": "playback_state", "state": payload}))
            for _message in connection:
                # ready/ended/error acknowledgements are accepted here. Python
                # keeps its duration watchdog so a closed Output cannot stall.
                pass
        except ConnectionClosed:
            pass
        finally:
            with self._ws_lock:
                self._ws_clients.discard(connection)

    def _broadcast_state(self) -> None:
        payload, _, _ = self.state.snapshot()
        message = json.dumps({"type": "playback_state", "state": payload})
        with self._ws_lock:
            clients = list(self._ws_clients)
        for connection in clients:
            try:
                connection.send(message)
            except (ConnectionClosed, OSError):
                with self._ws_lock:
                    self._ws_clients.discard(connection)

    def stop(self) -> None:
        server, thread = self._server, self._thread
        ws_server, ws_thread = self._ws_server, self._ws_thread
        self._server = None
        self._thread = None
        self._ws_server = None
        self._ws_thread = None
        if server:
            server.shutdown()
            server.server_close()
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        if ws_server:
            ws_server.shutdown()
        if ws_thread and ws_thread.is_alive():
            ws_thread.join(timeout=2.0)

    def set_idle_path(self, path: Path | None) -> None:
        self.state.set_idle_path(path)
        self._broadcast_state()

    def set_background_music(self, path: Path | None, muted: bool = False) -> None:
        self.state.set_background_music(path, muted=muted)
        self._broadcast_state()

    def set_idle_video_muted(self, muted: bool) -> None:
        self.state.set_idle_video_muted(muted)
        self._broadcast_state()

    def show_action(
        self,
        path: Path,
        sound_path: Path | None = None,
        label: str = "",
        preload_path: Path | None = None,
    ) -> None:
        self.state.show_action(path, sound_path=sound_path, label=label, preload_path=preload_path)
        self._broadcast_state()

    def show_idle(self, preload_path: Path | None = None) -> None:
        self.state.show_idle(preload_path=preload_path)
        self._broadcast_state()
