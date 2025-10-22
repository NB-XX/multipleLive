const { contextBridge, ipcRenderer } = require('electron');

// 暴露安全的API给渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  // 窗口控制
  minimizeWindow: () => ipcRenderer.invoke('window-minimize'),
  maximizeWindow: () => ipcRenderer.invoke('window-maximize'),
  closeWindow: () => ipcRenderer.invoke('window-close'),
  toggleAlwaysOnTop: () => ipcRenderer.invoke('window-toggle-always-on-top'),
  toggleFullscreen: () => ipcRenderer.invoke('window-toggle-fullscreen'),
  
  // 平台信息
  platform: process.platform,
  
  // 版本信息
  version: process.versions.electron
});
