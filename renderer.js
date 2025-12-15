// Get DOM elements
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const jobsCompletedEl = document.getElementById('jobs-completed');
const jobsFailedEl = document.getElementById('jobs-failed');
const earningsEl = document.getElementById('earnings');
const logsContainer = document.getElementById('logs-container');
const configForm = document.getElementById('config-form');
const startBtn = document.getElementById('start-btn');
const stopBtn = document.getElementById('stop-btn');
const clearLogsBtn = document.getElementById('clear-logs');
const refreshJobsBtn = document.getElementById('refresh-jobs');
const activeJobsList = document.getElementById('active-jobs-list');
const gpuStatusText = document.getElementById('gpu-status-text');
const gpuCount = document.getElementById('gpu-count');
const gpuList = document.getElementById('gpu-list');

// Initialize
let nodeStatus = {
  running: false,
  nodeId: null,
  connected: false,
  jobsCompleted: 0,
  jobsFailed: 0,
  earnings: 0,
  activeTrainingJobs: []
};

// Load app version
window.electronAPI.getAppVersion().then(version => {
  document.getElementById('app-version').textContent = `v${version}`;
});

// Wallet address
let walletAddress = null;
let walletNetwork = 'tron';

// Validate wallet address on input
document.addEventListener('DOMContentLoaded', () => {
  const walletInput = document.getElementById('wallet-address-input');
  if (walletInput) {
    walletInput.addEventListener('input', (e) => {
      const address = e.target.value.trim();
      if (address && address.startsWith('T') && address.length === 34) {
        walletAddress = address;
        walletNetwork = 'tron';
        e.target.style.borderColor = '#10b981';
      } else if (address) {
        e.target.style.borderColor = '#ef4444';
      } else {
        e.target.style.borderColor = '#d1d5db';
        walletAddress = null;
      }
    });
  }
});

// Event listeners
configForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  
  const walletInput = document.getElementById('wallet-address-input');
  if (walletInput && walletInput.value.trim()) {
    const address = walletInput.value.trim();
    if (address.startsWith('T') && address.length === 34) {
      walletAddress = address;
      walletNetwork = 'tron';
    }
  }
  
  const config = {
    nodeName: document.getElementById('node-name').value,
    description: document.getElementById('description').value,
    coordinatorUrl: document.getElementById('coordinator-url').value,
    walletAddress: walletAddress || '',
    walletNetwork: walletNetwork,
    gpuEnabled: document.getElementById('gpu-enabled').checked,
    maxConcurrentJobs: parseInt(document.getElementById('max-jobs').value),
    trainingFramework: document.getElementById('training-framework').value,
    storagePath: document.getElementById('storage-path').value
  };
  
  const result = await window.electronAPI.startNode(config);
  if (result.success) {
    addLog('Training node starting...', 'info');
    startBtn.disabled = true;
    stopBtn.disabled = false;
  } else {
    addLog(`Failed to start node: ${result.message}`, 'error');
    alert(`Failed to start node: ${result.message}`);
  }
});

stopBtn.addEventListener('click', async () => {
  const result = await window.electronAPI.stopNode();
  if (result.success) {
    addLog('Training node stopped', 'info');
    startBtn.disabled = false;
    stopBtn.disabled = true;
    updateStatus({ running: false, connected: false });
  }
});

clearLogsBtn.addEventListener('click', () => {
  logsContainer.innerHTML = '';
  addLog('Logs cleared', 'info');
});

refreshJobsBtn.addEventListener('click', () => {
  updateActiveJobs();
});

// Status update handler
window.electronAPI.onNodeStatusUpdate((status) => {
  nodeStatus = status;
  updateStatus(status);
  updateActiveJobs();
});

// Training progress handler
window.electronAPI.onTrainingProgress((progress) => {
  updateTrainingProgress(progress);
});

// Log handler
window.electronAPI.onNodeLog((log) => {
  addLog(log);
});

// Update status display
function updateStatus(status) {
  if (status.connected) {
    statusDot.className = 'status-dot connected';
    statusText.textContent = 'Connected';
  } else if (status.running) {
    statusDot.className = 'status-dot connecting';
    statusText.textContent = 'Connecting...';
  } else {
    statusDot.className = 'status-dot';
    statusText.textContent = 'Disconnected';
  }
  
  jobsCompletedEl.textContent = status.jobsCompleted || 0;
  jobsFailedEl.textContent = status.jobsFailed || 0;
  earningsEl.textContent = `${status.earnings || 0} USDT`;
  
  if (status.activeTrainingJobs) {
    nodeStatus.activeTrainingJobs = status.activeTrainingJobs;
    updateActiveJobs();
  }
}

// Update active training jobs
function updateActiveJobs() {
  const jobs = nodeStatus.activeTrainingJobs || [];
  
  if (jobs.length === 0) {
    activeJobsList.innerHTML = '<div class="empty-state">No active training jobs</div>';
    return;
  }
  
  activeJobsList.innerHTML = jobs.map(job => {
    const elapsed = job.startTime ? Math.floor((Date.now() - job.startTime) / 1000 / 60) : 0;
    const progress = job.progress || 0;
    
    return `
      <div class="job-card">
        <div class="job-header">
          <span class="job-id">Job: ${job.id}</span>
          <span class="job-status running">Running</span>
        </div>
        <div class="job-progress">
          <div class="progress-bar">
            <div class="progress-fill" style="width: ${progress}%"></div>
          </div>
          <div style="text-align: center; margin-top: 0.25rem; font-size: 0.75rem; color: var(--text-secondary);">
            ${progress.toFixed(1)}%
          </div>
        </div>
        <div class="job-metrics">
          <div class="metric">
            <div class="metric-label">Epoch</div>
            <div class="metric-value">${job.epoch || 0}/${job.totalEpochs || 0}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Loss</div>
            <div class="metric-value">${job.loss !== null ? job.loss.toFixed(4) : '-'}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Time</div>
            <div class="metric-value">${elapsed}m</div>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// Update training progress
function updateTrainingProgress(progress) {
  const jobs = nodeStatus.activeTrainingJobs || [];
  const job = jobs.find(j => j.id === progress.jobId);
  if (job) {
    if (progress.progress !== undefined) job.progress = progress.progress;
    if (progress.epoch !== undefined) job.epoch = progress.epoch;
    if (progress.totalEpochs !== undefined) job.totalEpochs = progress.totalEpochs;
    updateActiveJobs();
  }
}

// Add log entry
function addLog(message, type = 'info') {
  const logEntry = document.createElement('div');
  logEntry.className = `log-entry ${type}`;
  
  const timestamp = new Date().toLocaleTimeString();
  logEntry.textContent = `[${timestamp}] ${message}`;
  
  logsContainer.appendChild(logEntry);
  logsContainer.scrollTop = logsContainer.scrollHeight;
  
  // Keep only last 1000 log entries
  while (logsContainer.children.length > 1000) {
    logsContainer.removeChild(logsContainer.firstChild);
  }
}

// Update GPU status (placeholder - can be enhanced)
async function updateGPUStatus() {
  try {
    const gpuInfo = await window.electronAPI.getGPUInfo();
    if (gpuInfo.gpuEnabled) {
      gpuStatusText.textContent = 'Enabled';
      gpuCount.textContent = gpuInfo.totalGPUs || '0';
    } else {
      gpuStatusText.textContent = 'Disabled';
      gpuCount.textContent = '0';
    }
  } catch (error) {
    gpuStatusText.textContent = 'Unknown';
    gpuCount.textContent = '-';
  }
}

// Initialize
updateGPUStatus();
setInterval(updateGPUStatus, 5000); // Update every 5 seconds

// Initial status check
window.electronAPI.getNodeStatus().then(status => {
  if (status) {
    nodeStatus = status;
    updateStatus(status);
    if (status.running) {
      startBtn.disabled = true;
      stopBtn.disabled = false;
    }
  }
});

