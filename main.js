const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

let mainWindow;
let nodeProcess = null;
let nodeStatus = {
  running: false,
  nodeId: null,
  connected: false,
  jobsCompleted: 0,
  jobsFailed: 0,
  earnings: 0,
  activeTrainingJobs: []
};

// Check if running in development
const isDev = process.argv.includes('--dev');

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    icon: fs.existsSync(path.join(__dirname, 'assets', 'icon.png')) 
      ? path.join(__dirname, 'assets', 'icon.png')
      : undefined,
    titleBarStyle: 'default',
    show: false
  });

  mainWindow.loadFile('index.html');

  // Show window when ready
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    
    if (isDev) {
      mainWindow.webContents.openDevTools();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// App event handlers
app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  // Stop node process before quitting
  if (nodeProcess) {
    stopNode();
  }
  
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// IPC Handlers
ipcMain.handle('get-node-status', () => {
  return nodeStatus;
});

ipcMain.handle('check-setup', async () => {
  const nodeClientDir = path.resolve(__dirname, 'node-client');
  const venvPath = process.platform === 'win32' 
    ? path.join(nodeClientDir, 'venv', 'Scripts', 'python.exe')
    : path.join(nodeClientDir, 'venv', 'bin', 'python3');
  
  const requirementsPath = path.join(nodeClientDir, 'requirements.txt');
  const mainPyPath = path.join(nodeClientDir, 'src', 'main.py');
  
  return {
    venvExists: fs.existsSync(venvPath),
    requirementsExists: fs.existsSync(requirementsPath),
    mainPyExists: fs.existsSync(mainPyPath),
    nodeClientDir: nodeClientDir
  };
});

ipcMain.handle('start-node', async (event, config) => {
  if (nodeProcess) {
    return { success: false, message: 'Node is already running' };
  }

  try {
    // Create config file
    const configPath = path.join(app.getPath('userData'), 'training-node-config.json');
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2));

    // Start Python node client
    const nodeClientDir = path.resolve(__dirname, 'node-client');
    const nodeClientPath = path.join(nodeClientDir, 'src', 'main.py');
    
    // Check if node-client files exist
    if (!fs.existsSync(nodeClientPath)) {
      return { 
        success: false, 
        message: 'Node client files not found. Please ensure the app is properly installed.' 
      };
    }
    
    // Try to use venv Python first, then system Python
    let pythonPath = null;
    if (process.platform === 'win32') {
      const venvPython = path.join(nodeClientDir, 'venv', 'Scripts', 'python.exe');
      if (fs.existsSync(venvPython)) {
        pythonPath = venvPython;
      } else {
        try {
          require('child_process').execSync('python --version', { stdio: 'ignore' });
          pythonPath = 'python';
        } catch {
          try {
            require('child_process').execSync('py --version', { stdio: 'ignore' });
            pythonPath = 'py';
          } catch {
            try {
              require('child_process').execSync('python3 --version', { stdio: 'ignore' });
              pythonPath = 'python3';
            } catch {
              return { success: false, message: 'Python not found. Please install Python 3.11+' };
            }
          }
        }
      }
    } else {
      const venvPython = path.join(nodeClientDir, 'venv', 'bin', 'python3');
      if (fs.existsSync(venvPython)) {
        pythonPath = venvPython;
      } else {
        pythonPath = 'python3';
        try {
          require('child_process').execSync('python3 --version', { stdio: 'ignore' });
        } catch {
          return { success: false, message: 'Python not found. Please install Python 3.11+' };
        }
      }
    }
    const pythonPathEnv = process.env.PYTHONPATH || '';
    const newPythonPath = pythonPathEnv 
      ? `${nodeClientDir}${path.delimiter}${pythonPathEnv}`
      : nodeClientDir;

    // Set initial status - process is starting
    nodeStatus.running = true;
    nodeStatus.connected = false;
    mainWindow.webContents.send('node-status-update', nodeStatus);

    nodeProcess = spawn(pythonPath, ['-u', nodeClientPath], {
      cwd: nodeClientDir,
      env: {
        ...process.env,
        PYTHONPATH: newPythonPath,
        PYTHONUNBUFFERED: '1',
        COORDINATOR_URL: config.coordinatorUrl || 'https://backend.infitask.com',
        NODE_NAME: config.nodeName || 'My Training Node',
        NODE_DESCRIPTION: config.description || '',
        GPU_ENABLED: config.gpuEnabled ? 'true' : 'false',
        MAX_CONCURRENT_JOBS: config.maxConcurrentJobs?.toString() || '1',
        WALLET_ADDRESS: config.walletAddress || '',
        WALLET_NETWORK: config.walletNetwork || 'tron',
        NODE_TYPE: 'training'  // Mark as training node
      }
    });

    // Buffer for incomplete lines
    let outputBuffer = '';
    
    nodeProcess.stdout.on('data', (data) => {
      const output = data.toString();
      console.log('Node output:', output);
      
      // Add to buffer and process complete lines
      outputBuffer += output;
      const lines = outputBuffer.split('\n');
      outputBuffer = lines.pop() || '';
      
      // Process each complete line
      for (const line of lines) {
        const trimmedLine = line.trim();
        if (!trimmedLine) continue;
        
        // Check if node client is starting
        if (trimmedLine.includes('Starting AIForge Training Node Client')) {
          nodeStatus.running = true;
          mainWindow.webContents.send('node-status-update', nodeStatus);
        }
        
        // Check for registration success
        if (trimmedLine.includes('Node registered successfully') || 
            trimmedLine.includes('Node re-registered successfully')) {
          nodeStatus.running = true;
          nodeStatus.connected = true;
          if (!nodeStatus.nodeId) {
            const match = trimmedLine.match(/(node-[\w-]+)/);
            if (match) {
              nodeStatus.nodeId = match[1] || match[0];
            }
          }
          mainWindow.webContents.send('node-status-update', nodeStatus);
        }
        
        // Parse node ID
        if (trimmedLine.includes('Node ID:')) {
          let match = trimmedLine.match(/Node ID:\s*(node-[\w-]+)/i);
          if (!match) {
            match = trimmedLine.match(/Node ID:\s*([^\s\n]+)/i);
          }
          if (match) {
            nodeStatus.nodeId = match[1] || match[0];
            nodeStatus.running = true;
            nodeStatus.connected = true;
            mainWindow.webContents.send('node-status-update', nodeStatus);
          }
        }
        
        // Check for heartbeat
        if (trimmedLine.includes('Heartbeat sent')) {
          nodeStatus.connected = true;
          nodeStatus.running = true;
          mainWindow.webContents.send('node-status-update', nodeStatus);
        }
        
        // Parse training job start
        if (trimmedLine.includes('Executing training job') || trimmedLine.includes('Starting training job')) {
          const jobMatch = trimmedLine.match(/job[_-]?([\w-]+)/i);
          if (jobMatch) {
            const jobId = jobMatch[1];
            if (!nodeStatus.activeTrainingJobs.find(j => j.id === jobId)) {
              nodeStatus.activeTrainingJobs.push({
                id: jobId,
                progress: 0,
                epoch: 0,
                totalEpochs: 0,
                loss: null,
                startTime: Date.now()
              });
              mainWindow.webContents.send('node-status-update', nodeStatus);
            }
          }
        }
        
        // Parse training progress (e.g., "Progress: 50%" or "Epoch 3/5")
        const progressMatch = trimmedLine.match(/progress[:\s]+(\d+(?:\.\d+)?)%/i);
        if (progressMatch) {
          const progress = parseFloat(progressMatch[1]);
          if (nodeStatus.activeTrainingJobs.length > 0) {
            nodeStatus.activeTrainingJobs[nodeStatus.activeTrainingJobs.length - 1].progress = progress;
            mainWindow.webContents.send('training-progress', {
              jobId: nodeStatus.activeTrainingJobs[nodeStatus.activeTrainingJobs.length - 1].id,
              progress: progress
            });
            mainWindow.webContents.send('node-status-update', nodeStatus);
          }
        }
        
        // Parse epoch (e.g., "Epoch 3/5" or "Epoch: 3/5")
        const epochMatch = trimmedLine.match(/epoch[:\s]+(\d+)\/(\d+)/i);
        if (epochMatch) {
          const currentEpoch = parseInt(epochMatch[1]);
          const totalEpochs = parseInt(epochMatch[2]);
          if (nodeStatus.activeTrainingJobs.length > 0) {
            const job = nodeStatus.activeTrainingJobs[nodeStatus.activeTrainingJobs.length - 1];
            job.epoch = currentEpoch;
            job.totalEpochs = totalEpochs;
            job.progress = (currentEpoch / totalEpochs) * 100;
            mainWindow.webContents.send('training-progress', {
              jobId: job.id,
              progress: job.progress,
              epoch: currentEpoch,
              totalEpochs: totalEpochs
            });
            mainWindow.webContents.send('node-status-update', nodeStatus);
          }
        }
        
        // Parse loss (e.g., "Loss: 0.45" or "loss = 0.45")
        const lossMatch = trimmedLine.match(/loss[:\s=]+(\d+\.?\d*)/i);
        if (lossMatch) {
          const loss = parseFloat(lossMatch[1]);
          if (nodeStatus.activeTrainingJobs.length > 0) {
            nodeStatus.activeTrainingJobs[nodeStatus.activeTrainingJobs.length - 1].loss = loss;
            mainWindow.webContents.send('node-status-update', nodeStatus);
          }
        }
        
        // Parse training completion
        if (trimmedLine.includes('Training completed successfully') || 
            trimmedLine.includes('Job') && trimmedLine.includes('completed successfully')) {
          const jobMatch = trimmedLine.match(/job[_-]?([\w-]+)/i);
          if (jobMatch) {
            const jobId = jobMatch[1];
            nodeStatus.activeTrainingJobs = nodeStatus.activeTrainingJobs.filter(j => j.id !== jobId);
            nodeStatus.jobsCompleted++;
            mainWindow.webContents.send('node-status-update', nodeStatus);
          }
        }
        
        // Parse training failure
        if (trimmedLine.includes('Training job') && trimmedLine.includes('failed') ||
            trimmedLine.includes('Job') && trimmedLine.includes('failed')) {
          const jobMatch = trimmedLine.match(/job[_-]?([\w-]+)/i);
          if (jobMatch) {
            const jobId = jobMatch[1];
            nodeStatus.activeTrainingJobs = nodeStatus.activeTrainingJobs.filter(j => j.id !== jobId);
            nodeStatus.jobsFailed++;
            mainWindow.webContents.send('node-status-update', nodeStatus);
          }
        }
      }
      
      // Also check raw output for immediate detection
      if (output.includes('Node registered successfully') || 
          output.includes('Node re-registered successfully') ||
          output.includes('Heartbeat sent')) {
        nodeStatus.running = true;
        nodeStatus.connected = true;
        if (!nodeStatus.nodeId) {
          const match = output.match(/Node ID:\s*(node-[\w-]+)/i);
          if (match) {
            nodeStatus.nodeId = match[1] || match[0];
          }
        }
        mainWindow.webContents.send('node-status-update', nodeStatus);
      }
      
      // Send log to renderer
      mainWindow.webContents.send('node-log', output);
    });

    nodeProcess.stderr.on('data', (data) => {
      const error = data.toString();
      console.error('Node error:', error);
      mainWindow.webContents.send('node-log', `ERROR: ${error}`);
      
      // Check for registration failures
      if (error.includes('Registration failed') || error.includes('Failed to register')) {
        nodeStatus.connected = false;
        nodeStatus.running = false;
        mainWindow.webContents.send('node-status-update', nodeStatus);
      }
    });

    nodeProcess.on('close', (code) => {
      console.log(`Node process exited with code ${code}`);
      nodeStatus.running = false;
      nodeStatus.connected = false;
      nodeProcess = null;
      mainWindow.webContents.send('node-status-update', nodeStatus);
      mainWindow.webContents.send('node-log', `Node process exited with code ${code}`);
    });

    nodeProcess.on('error', (error) => {
      console.error('Failed to start node process:', error);
      nodeStatus.running = false;
      nodeStatus.connected = false;
      nodeProcess = null;
      mainWindow.webContents.send('node-status-update', nodeStatus);
      mainWindow.webContents.send('node-log', `ERROR: Failed to start node process: ${error.message}`);
    });

    return { success: true, message: 'Training node started successfully' };
  } catch (error) {
    console.error('Error starting node:', error);
    return { success: false, message: error.message };
  }
});

ipcMain.handle('stop-node', async () => {
  if (!nodeProcess) {
    return { success: false, message: 'Node is not running' };
  }

  try {
    nodeProcess.kill();
    nodeProcess = null;
    nodeStatus.running = false;
    nodeStatus.connected = false;
    return { success: true, message: 'Node stopped successfully' };
  } catch (error) {
    return { success: false, message: error.message };
  }
});

ipcMain.handle('open-external', async (event, url) => {
  // Validate URL to prevent protocol-based attacks
  try {
    const parsedUrl = new URL(url);
    // Only allow http and https protocols
    if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
      console.error('Invalid URL protocol:', parsedUrl.protocol);
      return { success: false, error: 'Invalid URL protocol. Only http and https are allowed.' };
    }
    await shell.openExternal(url);
    return { success: true };
  } catch (error) {
    console.error('Invalid URL:', error);
    return { success: false, error: 'Invalid URL format' };
  }
});

ipcMain.handle('get-app-version', () => {
  return app.getVersion();
});

// GPU monitoring (placeholder - can be enhanced with actual GPU detection)
ipcMain.handle('get-gpu-info', async () => {
  try {
    // This would query the Python client for GPU info
    // For now, return placeholder
    return {
      gpus: [],
      totalGPUs: 0,
      gpuEnabled: nodeStatus.running
    };
  } catch (error) {
    return { gpus: [], totalGPUs: 0, gpuEnabled: false };
  }
});

// Training job management
ipcMain.handle('get-active-training-jobs', () => {
  return nodeStatus.activeTrainingJobs;
});

ipcMain.handle('cancel-training-job', async (event, jobId) => {
  // This would send a cancel signal to the Python client
  // For now, just remove from active jobs
  nodeStatus.activeTrainingJobs = nodeStatus.activeTrainingJobs.filter(j => j.id !== jobId);
  mainWindow.webContents.send('node-status-update', nodeStatus);
  return { success: true };
});

function stopNode() {
  if (nodeProcess) {
    nodeProcess.kill();
    nodeProcess = null;
  }
}

