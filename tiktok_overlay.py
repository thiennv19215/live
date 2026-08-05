"""Local browser overlay output for TikTok Live Studio."""

from __future__ import annotations

import contextlib
import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


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
      background: #000;
      opacity: 0;
      transition: opacity 120ms linear;
    }
    .media.active { opacity: 1; }
    #status {
      position: absolute;
      left: 50%;
      bottom: 4vh;
      z-index: 3;
      max-width: 82%;
      transform: translateX(-50%);
      padding: 12px 18px;
      border: 1px solid rgba(255,255,255,.16);
      border-radius: 999px;
      background: rgba(5,10,18,.78);
      color: #d9f7ff;
      font: 600 clamp(14px, 2vw, 28px)/1.2 "Segoe UI", sans-serif;
      letter-spacing: .02em;
      text-align: center;
      backdrop-filter: blur(14px);
      opacity: 0;
      transition: opacity 180ms ease;
    }
    #status.visible { opacity: 1; }
  </style>
</head>
<body>
  <main>
    <video id="video" class="media" autoplay playsinline></video>
    <img id="image" class="media" alt="">
    <audio id="sound" preload="auto"></audio>
    <div id="status">Waiting for media</div>
  </main>
  <script>
    const query = new URLSearchParams(location.search);
    const debug = query.get("debug") === "1";
    const muted = query.get("muted") === "1";
    const mediaFit = query.get("fit") === "contain" ? "contain" : "cover";
    document.documentElement.style.setProperty("--media-fit", mediaFit);
    const video = document.querySelector("#video");
    const image = document.querySelector("#image");
    const sound = document.querySelector("#sound");
    const status = document.querySelector("#status");
    let currentVersion = -1;

    function showStatus(text, force = false) {
      status.textContent = text;
      status.classList.toggle("visible", force || debug);
    }

    function hideMedia() {
      video.classList.remove("active");
      image.classList.remove("active");
      video.pause();
      video.removeAttribute("src");
      image.removeAttribute("src");
      sound.pause();
      sound.removeAttribute("src");
    }

    async function applyState(state) {
      if (state.version === currentVersion) return;
      currentVersion = state.version;
      hideMedia();
      showStatus(`${state.mode.toUpperCase()} - ${state.label || "No media"}`, !state.media_url);
      if (!state.media_url) return;

      const mediaUrl = `${state.media_url}?v=${state.version}`;
      if (state.media_type === "image") {
        image.src = mediaUrl;
        image.classList.add("active");
      } else {
        video.loop = state.mode === "idle";
        video.muted = muted;
        video.src = mediaUrl;
        video.classList.add("active");
        try { await video.play(); } catch (error) { showStatus(`Playback blocked: ${error.message}`, true); }
      }

      if (state.sound_url && !muted) {
        sound.src = `${state.sound_url}?v=${state.version}`;
        try { await sound.play(); } catch (error) { if (debug) showStatus(`Audio blocked: ${error.message}`, true); }
      }
    }

    async function refresh() {
      try {
        const response = await fetch("/api/state", { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        await applyState(await response.json());
      } catch (error) {
        showStatus(`Overlay disconnected: ${error.message}`, true);
      }
    }

    refresh();
    setInterval(refresh, 200);
  </script>
</body>
</html>
"""


class OverlayState:
    def __init__(self, idle_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._idle_path = Path(idle_path).resolve() if idle_path else None
        self._action_path: Path | None = None
        self._sound_path: Path | None = None
        self._mode = "idle"
        self._label = self._idle_path.name if self._idle_path else "No idle media"
        self._version = 1

    def set_idle_path(self, path: Path | None) -> None:
        resolved = Path(path).resolve() if path else None
        with self._lock:
            self._idle_path = resolved
            if self._mode == "idle":
                self._label = resolved.name if resolved else "No idle media"
                self._version += 1

    def show_action(self, path: Path, sound_path: Path | None = None, label: str = "") -> None:
        with self._lock:
            self._action_path = Path(path).resolve()
            self._sound_path = Path(sound_path).resolve() if sound_path else None
            self._mode = "action"
            self._label = label or self._action_path.name
            self._version += 1

    def show_idle(self) -> None:
        with self._lock:
            self._action_path = None
            self._sound_path = None
            self._mode = "idle"
            self._label = self._idle_path.name if self._idle_path else "No idle media"
            self._version += 1

    def snapshot(self) -> tuple[dict[str, object], Path | None, Path | None]:
        with self._lock:
            media_path = self._action_path if self._mode == "action" else self._idle_path
            sound_path = self._sound_path if self._mode == "action" else None
            media_exists = bool(media_path and media_path.is_file())
            sound_exists = bool(sound_path and sound_path.is_file())
            payload: dict[str, object] = {
                "mode": self._mode if media_exists else "empty",
                "label": self._label,
                "version": self._version,
                "media_type": "image" if media_path and media_path.suffix.lower() in IMAGE_EXTENSIONS else "video",
                "media_url": "/media/current" if media_exists else "",
                "sound_url": "/audio/current" if sound_exists else "",
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
            self._send_bytes(OVERLAY_HTML.encode("utf-8"), "text/html; charset=utf-8", send_body, no_store=True)
            return
        if path == "/health":
            self._send_bytes(b"ok", "text/plain; charset=utf-8", send_body)
            return
        payload, media_path, sound_path = self.server.overlay.state.snapshot()
        if path == "/api/state":
            self._send_bytes(json.dumps(payload).encode("utf-8"), "application/json", send_body, no_store=True)
            return
        if path == "/media/current" and media_path:
            self._send_file(media_path, send_body)
            return
        if path == "/audio/current" and sound_path:
            self._send_file(sound_path, send_body)
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
            self.wfile.write(data)

    def _send_file(self, path: Path, send_body: bool) -> None:
        size = path.stat().st_size
        start, end = 0, max(size - 1, 0)
        status = 200
        range_header = self.headers.get("Range", "")
        if range_header.startswith("bytes="):
            with contextlib.suppress(ValueError):
                raw_start, raw_end = range_header[6:].split("-", 1)
                start = int(raw_start) if raw_start else 0
                end = int(raw_end) if raw_end else end
                start = max(0, min(start, end))
                end = min(end, size - 1)
                status = 206
        length = max(end - start + 1, 0)
        self.send_response(status)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store, max-age=0")
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
                except (BrokenPipeError, ConnectionResetError):
                    break
                remaining -= len(chunk)


class LocalOverlayServer:
    def __init__(self, idle_path: Path | None = None, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self.state = OverlayState(idle_path)
        self._server: _OverlayHttpServer | None = None
        self._thread: threading.Thread | None = None

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
        return self.url

    def stop(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server:
            server.shutdown()
            server.server_close()
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

    def set_idle_path(self, path: Path | None) -> None:
        self.state.set_idle_path(path)

    def show_action(self, path: Path, sound_path: Path | None = None, label: str = "") -> None:
        self.state.show_action(path, sound_path=sound_path, label=label)

    def show_idle(self) -> None:
        self.state.show_idle()
