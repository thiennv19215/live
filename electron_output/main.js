const fs = require("node:fs");
const crypto = require("node:crypto");
const http = require("node:http");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { app, BrowserWindow, dialog, ipcMain, screen, shell } = require("electron");
const { fitToWorkArea, parseOptions } = require("./window-options");

const logPath = path.join(process.env.TEMP || process.cwd(), "tiktok-live-control-room.log");
const isOutputOnly = process.argv.some((value) => value === "--output-only" || value === "--url" || value.startsWith("--url="));
const isDevRenderer = Boolean(process.env.ELECTRON_RENDERER_URL);
const backendPort = Number(process.env.BACKEND_PORT || (isDevRenderer ? 8776 : 8766));
const backendUrl = `http://127.0.0.1:${backendPort}`;
if (isDevRenderer) {
  app.setPath("userData", path.join(app.getPath("appData"), "TikTok Live Control Room Dev"));
}
let controllerWindow = null;
let outputWindow = null;
let backendProcess = null;
let controlServer = null;
let quitting = false;

function log(message) {
  fs.appendFileSync(logPath, `${new Date().toISOString()} ${message}\n`);
}

log(`startup argv=${JSON.stringify(process.argv)} outputOnly=${isOutputOnly} dev=${isDevRenderer}`);

process.on("uncaughtException", (error) => log(`uncaughtException: ${error.stack || error}`));
process.on("unhandledRejection", (error) => log(`unhandledRejection: ${error?.stack || error}`));
app.commandLine.appendSwitch("autoplay-policy", "no-user-gesture-required");
app.disableHardwareAcceleration();
app.setName(isOutputOnly ? "TikTok Live Output" : "TikTok Live Control Room");
app.setAppUserModelId("io.streamtoearn.tiktok-live-control-room");

function isAllowedUrl(value) {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" && ["127.0.0.1", "localhost"].includes(parsed.hostname);
  } catch {
    return false;
  }
}

function startControlServer(port) {
  if (!port) return;
  controlServer = http.createServer((request, response) => {
    if (request.url === "/status") {
      response.writeHead(200, { "Content-Type": "text/plain" });
      response.end("running");
      return;
    }
    if (request.url === "/close") {
      response.writeHead(200, { "Content-Type": "text/plain" });
      response.end("closing");
      setImmediate(() => app.quit());
      return;
    }
    response.writeHead(404);
    response.end();
  });
  controlServer.listen(port, "127.0.0.1");
}

function secureLocalNavigation(window) {
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event, targetUrl) => {
    if (!targetUrl.startsWith("file:") && !isAllowedUrl(targetUrl)) event.preventDefault();
  });
}

function loadUrlWithTimeout(window, url, timeoutMs = 8000) {
  let timer;
  return Promise.race([
    window.loadURL(url),
    new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`Output load timed out after ${timeoutMs}ms`)), timeoutMs);
    }),
  ]).finally(() => clearTimeout(timer));
}

async function createOutputWindow(options, standalone = false) {
  if (!isAllowedUrl(options.url)) throw new Error("Only localhost overlay URLs are allowed");
  if (outputWindow && !outputWindow.isDestroyed()) outputWindow.destroy();

  const display = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
  const size = fitToWorkArea(options.width, options.height, display.workAreaSize);
  outputWindow = new BrowserWindow({
    width: size.width,
    height: size.height,
    minWidth: 240,
    minHeight: 240,
    useContentSize: true,
    frame: false,
    backgroundColor: "#000000",
    title: `TikTok Live Output ${options.ratio}`,
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      devTools: false,
    },
  });
  outputWindow.setAspectRatio(options.width / options.height);
  outputWindow.setMenu(null);
  secureLocalNavigation(outputWindow);
  outputWindow.on("page-title-updated", (event) => {
    event.preventDefault();
    outputWindow?.setTitle(`TikTok Live Output ${options.ratio}`);
  });
  outputWindow.webContents.on("before-input-event", (event, input) => {
    if (input.key === "Escape") outputWindow?.close();
    if (input.key === "F11") {
      event.preventDefault();
      outputWindow?.setFullScreen(!outputWindow.isFullScreen());
    }
  });
  outputWindow.webContents.on("context-menu", (event) => event.preventDefault());
  outputWindow.webContents.once("did-finish-load", async () => {
    await outputWindow?.webContents.insertCSS(`
      html, body { -webkit-app-region: drag; cursor: default !important; overflow: hidden !important; }
      video, img, canvas { pointer-events: none !important; }
    `);
  });
  outputWindow.once("ready-to-show", () => outputWindow?.show());
  outputWindow.on("closed", () => {
    outputWindow = null;
    if (controllerWindow && !controllerWindow.isDestroyed()) {
      controllerWindow.webContents.send("output:closed");
    }
    if (standalone) app.quit();
  });
  try {
    await loadUrlWithTimeout(outputWindow, options.url);
  } catch (error) {
    outputWindow?.destroy();
    outputWindow = null;
    throw error;
  }
  return { open: true, title: outputWindow.getTitle() };
}

function releaseDirectory() {
  return process.env.PORTABLE_EXECUTABLE_DIR || path.dirname(process.execPath);
}

function runtimeDataDirectory() {
  return app.isPackaged ? app.getPath("userData") : path.resolve(__dirname, "..");
}

function seedRuntimeData() {
  const targetRoot = runtimeDataDirectory();
  fs.mkdirSync(targetRoot, { recursive: true });
  for (const name of ["gift_config.json", "action_presets.json", "obs_config.json"]) {
    const source = path.join(releaseDirectory(), name);
    const target = path.join(targetRoot, name);
    if (!fs.existsSync(target) && fs.existsSync(source)) fs.copyFileSync(source, target);
  }
  const sourceVideos = path.join(releaseDirectory(), "videos");
  const targetVideos = path.join(targetRoot, "videos");
  fs.mkdirSync(targetVideos, { recursive: true });
  if (fs.existsSync(sourceVideos)) fs.cpSync(sourceVideos, targetVideos, { recursive: true, force: false });
}

function videosDirectory() {
  return path.join(runtimeDataDirectory(), "videos");
}

function fileDigest(filePath) {
  const hash = crypto.createHash("sha256");
  const descriptor = fs.openSync(filePath, "r");
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  try {
    let bytesRead;
    do {
      bytesRead = fs.readSync(descriptor, buffer, 0, buffer.length, null);
      if (bytesRead) hash.update(buffer.subarray(0, bytesRead));
    } while (bytesRead);
  } finally {
    fs.closeSync(descriptor);
  }
  return hash.digest("hex");
}

function importMedia(sourcePath) {
  const source = path.resolve(sourcePath);
  const targetDirectory = videosDirectory();
  fs.mkdirSync(targetDirectory, { recursive: true });
  const parsed = path.parse(source);
  let target = path.join(targetDirectory, parsed.base);
  if (path.resolve(target).toLowerCase() === source.toLowerCase()) return source;
  let suffix = 2;
  while (fs.existsSync(target)) {
    const existing = fs.statSync(target);
    const incoming = fs.statSync(source);
    if (existing.size === incoming.size) {
      if (fileDigest(target) === fileDigest(source)) return target;
    }
    target = path.join(targetDirectory, `${parsed.name}-${suffix}${parsed.ext}`);
    suffix += 1;
  }
  fs.copyFileSync(source, target);
  return target;
}

function startBackend() {
  const packagedBackend = path.join(process.resourcesPath, "TikTokLiveBackend", "TikTokLiveBackend.exe");
  if (app.isPackaged && fs.existsSync(packagedBackend)) {
    backendProcess = spawn(packagedBackend, ["--port", String(backendPort)], {
      cwd: releaseDirectory(),
      env: { ...process.env, TIKTOK_LIVE_DATA_DIR: runtimeDataDirectory() },
      windowsHide: true,
      stdio: "ignore",
    });
  } else {
    const repoRoot = path.resolve(__dirname, "..");
    const backendEnv = { ...process.env };
    backendProcess = spawn(process.env.PYTHON_EXECUTABLE || "python", [path.join(repoRoot, "tiktok_backend.py"), "--port", String(backendPort)], {
      cwd: repoRoot,
      env: backendEnv,
      windowsHide: true,
      stdio: "ignore",
    });
  }
  backendProcess.on("error", (error) => log(`backend spawn error: ${error.stack || error}`));
  backendProcess.on("exit", (code) => log(`backend exited code=${code}`));
}

function requestBackendShutdown() {
  const request = http.request(`${backendUrl}/api/shutdown`, { method: "POST", timeout: 700 }, (response) => response.resume());
  request.on("error", () => {});
  request.end("{}");
}

function registerControllerIpc() {
  ipcMain.handle("output:open", (_event, options) => createOutputWindow(options));
  ipcMain.handle("output:close", () => {
    outputWindow?.close();
    return { open: false };
  });
  ipcMain.handle("output:status", () => ({ open: Boolean(outputWindow && !outputWindow.isDestroyed()) }));
  ipcMain.handle("dialog:pick-media", async (_event, options = {}) => {
    const multiple = Boolean(options.multiple);
    const result = await dialog.showOpenDialog(controllerWindow, {
      title: options.title || "Chọn video",
      properties: multiple ? ["openFile", "multiSelections"] : ["openFile"],
      filters: [
        options.kind === "audio"
          ? { name: "Audio", extensions: ["mp3", "wav", "m4a", "aac", "ogg", "flac"] }
          : { name: "Video / image", extensions: ["mp4", "mov", "mkv", "webm", "png", "jpg", "jpeg", "webp"] },
        { name: "All files", extensions: ["*"] },
      ],
    });
    if (result.canceled) return multiple ? [] : "";
    const selected = options.copyToLibrary ? result.filePaths.map(importMedia) : result.filePaths;
    return multiple ? selected : selected[0];
  });
  ipcMain.handle("shell:open-videos", () => shell.openPath(videosDirectory()));
  ipcMain.on("window:minimize", () => controllerWindow?.minimize());
  ipcMain.on("window:toggle-maximize", () => {
    if (controllerWindow?.isMaximized()) controllerWindow.unmaximize();
    else controllerWindow?.maximize();
  });
  ipcMain.on("window:close", () => controllerWindow?.close());
}

async function createControllerWindow() {
  seedRuntimeData();
  startBackend();
  registerControllerIpc();
  const workArea = screen.getPrimaryDisplay().workAreaSize;
  const windowWidth = Math.min(1440, Math.max(900, workArea.width - 24));
  const windowHeight = Math.min(900, Math.max(680, workArea.height - 24));
  controllerWindow = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    minWidth: Math.min(1100, windowWidth),
    minHeight: Math.min(720, windowHeight),
    center: true,
    frame: false,
    backgroundColor: "#071018",
    show: true,
    title: "TikTok Live Control Room",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      additionalArguments: [`--backend-url=${backendUrl}`],
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  controllerWindow.setMenu(null);
  secureLocalNavigation(controllerWindow);
  controllerWindow.once("ready-to-show", () => controllerWindow?.show());
  const visibilityWatchdog = setInterval(() => {
    if (controllerWindow && !controllerWindow.isDestroyed() && !controllerWindow.isVisible() && !controllerWindow.isMinimized()) {
      controllerWindow.show();
      controllerWindow.focus();
    }
  }, 1000);
  controllerWindow.on("closed", () => {
    clearInterval(visibilityWatchdog);
    controllerWindow = null;
    if (!quitting) app.quit();
  });
  const devUrl = process.env.ELECTRON_RENDERER_URL;
  if (devUrl) await controllerWindow.loadURL(devUrl);
  else await controllerWindow.loadFile(path.join(__dirname, "renderer", "dist", "index.html"));
  // Some Windows GPU/frameless combinations do not emit ready-to-show even
  // though the renderer has finished loading. Always reveal the controller
  // after navigation so dev startup cannot remain hidden in the taskbar.
  if (controllerWindow && !controllerWindow.isDestroyed()) {
    controllerWindow.show();
    controllerWindow.focus();
  }
}

app.whenReady().then(async () => {
  if (isOutputOnly) {
    const options = parseOptions(process.argv);
    startControlServer(options.controlPort);
    await createOutputWindow(options, true);
    return;
  }
  if (!app.requestSingleInstanceLock()) {
    app.quit();
    return;
  }
  app.on("second-instance", () => {
    if (controllerWindow?.isMinimized()) controllerWindow.restore();
    controllerWindow?.focus();
  });
  await createControllerWindow();
}).catch((error) => {
  log(`startup error: ${error.stack || error}`);
  app.quit();
});

app.on("before-quit", () => {
  quitting = true;
  if (controlServer) controlServer.close();
  if (!isOutputOnly) requestBackendShutdown();
  if (backendProcess && !backendProcess.killed) {
    setTimeout(() => backendProcess?.kill(), 900).unref();
  }
});

app.on("window-all-closed", () => app.quit());
