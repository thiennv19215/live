const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktop", {
  backendUrl: "http://127.0.0.1:8766",
  openOutput: (options) => ipcRenderer.invoke("output:open", options),
  closeOutput: () => ipcRenderer.invoke("output:close"),
  getOutputStatus: () => ipcRenderer.invoke("output:status"),
  pickMedia: () => ipcRenderer.invoke("dialog:pick-media"),
  openVideosFolder: () => ipcRenderer.invoke("shell:open-videos"),
  minimize: () => ipcRenderer.send("window:minimize"),
  toggleMaximize: () => ipcRenderer.send("window:toggle-maximize"),
  close: () => ipcRenderer.send("window:close"),
});
