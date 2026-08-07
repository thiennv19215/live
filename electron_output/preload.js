const { contextBridge, ipcRenderer } = require("electron");

const backendArg = process.argv.find((value) => value.startsWith("--backend-url="));
const backendUrl = backendArg ? backendArg.slice("--backend-url=".length) : "http://127.0.0.1:8766";

contextBridge.exposeInMainWorld("desktop", {
  backendUrl,
  openOutput: (options) => ipcRenderer.invoke("output:open", options),
  closeOutput: () => ipcRenderer.invoke("output:close"),
  setOutputHidden: (hidden) => ipcRenderer.invoke("output:set-hidden", hidden),
  getOutputStatus: () => ipcRenderer.invoke("output:status"),
  onOutputClosed: (callback) => {
    const listener = () => callback();
    ipcRenderer.on("output:closed", listener);
    return () => ipcRenderer.removeListener("output:closed", listener);
  },
  pickMedia: (options = {}) => ipcRenderer.invoke("dialog:pick-media", options),
  pickFolder: (options = {}) => ipcRenderer.invoke("dialog:pick-folder", options),
  openVideosFolder: () => ipcRenderer.invoke("shell:open-videos"),
  minimize: () => ipcRenderer.send("window:minimize"),
  toggleMaximize: () => ipcRenderer.send("window:toggle-maximize"),
  close: () => ipcRenderer.send("window:close"),
});
