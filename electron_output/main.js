const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { app, BrowserWindow, screen } = require("electron");
const { fitToWorkArea, parseOptions } = require("./window-options");

const logPath = path.join(process.env.TEMP || process.cwd(), "tiktok-live-output.log");
function log(message) {
  fs.appendFileSync(logPath, `${new Date().toISOString()} ${message}\n`);
}
process.on("uncaughtException", (error) => log(`uncaughtException: ${error.stack || error}`));
process.on("unhandledRejection", (error) => log(`unhandledRejection: ${error?.stack || error}`));
log(`start argv=${JSON.stringify(process.argv)}`);

app.commandLine.appendSwitch("autoplay-policy", "no-user-gesture-required");
app.setName("TikTok Live Output");
app.setAppUserModelId("io.streamtoearn.tiktok-live-output");

let outputWindow = null;
let controlServer = null;

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

function isAllowedUrl(value) {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" && ["127.0.0.1", "localhost"].includes(parsed.hostname);
  } catch {
    return false;
  }
}

async function createOutputWindow() {
  const options = parseOptions(process.argv);
  log(`options=${JSON.stringify(options)}`);
  startControlServer(options.controlPort);
  if (!isAllowedUrl(options.url)) throw new Error("Only localhost overlay URLs are allowed");

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
  outputWindow.on("page-title-updated", (event) => {
    event.preventDefault();
    outputWindow.setTitle(`TikTok Live Output ${options.ratio}`);
  });
  outputWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  outputWindow.webContents.on("will-navigate", (event, targetUrl) => {
    if (!isAllowedUrl(targetUrl)) event.preventDefault();
  });
  outputWindow.webContents.on("before-input-event", (event, input) => {
    if (input.key === "Escape") outputWindow.close();
    if (input.key === "F11") {
      event.preventDefault();
      outputWindow.setFullScreen(!outputWindow.isFullScreen());
    }
  });
  outputWindow.webContents.on("context-menu", (event) => event.preventDefault());
  outputWindow.webContents.once("did-finish-load", async () => {
    await outputWindow.webContents.insertCSS(`
      html, body { -webkit-app-region: drag; cursor: default !important; overflow: hidden !important; }
      video, img, canvas { pointer-events: none !important; }
    `);
  });
  outputWindow.once("ready-to-show", () => outputWindow.show());
  outputWindow.on("closed", () => { outputWindow = null; });
  await outputWindow.loadURL(options.url);
  log("overlay loaded");
}

app.whenReady().then(createOutputWindow).catch((error) => {
  log(`startup error: ${error.stack || error}`);
  console.error(error);
  app.quit();
});

app.on("window-all-closed", () => app.quit());
app.on("before-quit", () => {
  if (controlServer) controlServer.close();
});
