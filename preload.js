const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('electronAPI', {
  getNodeStatus: () => ipcRenderer.invoke('get-node-status'),
  checkSetup: () => ipcRenderer.invoke('check-setup'),
  startNode: (config) => ipcRenderer.invoke('start-node', config),
  stopNode: () => ipcRenderer.invoke('stop-node'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  
  // GPU monitoring
  getGPUInfo: () => ipcRenderer.invoke('get-gpu-info'),
  
  // Training job management
  getActiveTrainingJobs: () => ipcRenderer.invoke('get-active-training-jobs'),
  cancelTrainingJob: (jobId) => ipcRenderer.invoke('cancel-training-job', jobId),
  
  // Event listeners
  onNodeStatusUpdate: (callback) => {
    ipcRenderer.on('node-status-update', (event, status) => callback(status));
  },
  onNodeLog: (callback) => {
    ipcRenderer.on('node-log', (event, log) => callback(log));
  },
  onTrainingProgress: (callback) => {
    ipcRenderer.on('training-progress', (event, progress) => callback(progress));
  },
  
  // Remove listeners
  removeAllListeners: (channel) => {
    ipcRenderer.removeAllListeners(channel);
  }
});

