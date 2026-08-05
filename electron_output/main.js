const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { app, BrowserWindow, dialog, ipcMain, screen, shell } = require("electron");
const { fitToWorkArea, parseOptions } = require("./window-options");

const logPath = path.join(process.env.TEMP || process.cwd(), "tiktok-live-control-room.log");
const isOutputOnly = process.argv.some((value) => value === "--output-only" || value === "--url" || value.startsWith("--url="));
const backendUrl = "http://127.0.0.1:8766";
let controllerWindow = null;
let outputWindow = null;
let backendProcess = null;
let controlServer = null;
let quitting = false;

function log(message) {
  fs.appendFileSync(logPath, `${new Date().toISOString()} ${message}\n`);
}

process.on("uncaughtException", (error) => log(`uncaughtException: ${error.stack || error}`));
process.on("unhandledRejection", (error) => log(`unhandledRejection: ${error?.stack || error}`));
app.commandLine.appendSwitch("autoplay-policy", "no-user-gesture-required");
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
    if (standalone) app.quit();
  });
  await outputWindow.loadURL(options.url);
  return { open: true, title: outputWindow.getTitle() };
}

function releaseDirectory() {
  return process.env.PORTABLE_EXECUTABLE_DIR || path.dirname(process.execPath);
}

function videosDirectory() {
  return app.isPackaged ? path.join(releaseDirectory(), "videos") : path.resolve(__dirname, "..", "videos");
}

function startBackend() {
  const packagedBackend = path.join(releaseDirectory(), "TikTokLiveBackend.exe");
  if (app.isPackaged && fs.existsSync(packagedBackend)) {
    backendProcess = spawn(packagedBackend, ["--port", "8766"], { windowsHide: true, stdio: "ignore" });
  } else {
    const repoRoot = path.resolve(__dirname, "..");
    backendProcess = spawn("python", [path.join(repoRoot, "tiktok_backend.py"), "--port", "8766"], {
      cwd: repoRoot,
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
  ipcMain.handle("dialog:pick-media", async () => {
    const result = await dialog.showOpenDialog(controllerWindow, {
      title: "Chọn video nền",
      properties: ["openFile"],
      filters: [
        { name: "Media", extensions: ["mp4", "mov", "mkv", "webm", "png", "jpg", "jpeg", "webp"] },
        { name: "All files", extensions: ["*"] },
      ],
    });
    return result.canceled ? "" : result.filePaths[0];
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
    show: false,
    title: "TikTok Live Control Room",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  controllerWindow.setMenu(null);
  secureLocalNavigation(controllerWindow);
  controllerWindow.once("ready-to-show", () => controllerWindow?.show());
  controllerWindow.on("closed", () => {
    controllerWindow = null;
    if (!quitting) app.quit();
  });
  const devUrl = process.env.ELECTRON_RENDERER_URL;
  if (devUrl) await controllerWindow.loadURL(devUrl);
  else await controllerWindow.loadFile(path.join(__dirname, "renderer", "dist", "index.html"));
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
