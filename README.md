# AIForge Training Node - Desktop Application

Cross-platform desktop application for running AIForge Network training nodes.

## Features

- 🎓 **Training-Focused**: Dedicated to training/finetune jobs only
- 🖥️ **Cross-Platform**: Windows, macOS, and Linux support
- 🎨 **Modern UI**: Clean and intuitive interface for training jobs
- ⚡ **Easy Setup**: Simple configuration and one-click start
- 📊 **Real-time Monitoring**: Monitor GPU usage, training progress, and metrics
- 📝 **Live Logs**: View training logs in real-time
- 🔧 **GPU Management**: Monitor GPU resources and usage

## Installation

### Development

1. Install dependencies:
```bash
npm install
```

2. Set up Python node client:
```bash
cd node-client
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Start the app:
```bash
npm start
```

### Building Installers

#### Windows
```bash
npm run build:win
```
Creates a `.exe` installer in the `dist` folder.

#### macOS
```bash
npm run build:mac
```
Creates a `.dmg` file in the `dist` folder.

#### Linux
```bash
npm run build:linux
```
Creates `.AppImage` and `.deb` packages in the `dist` folder.

## Configuration

The app requires:
- Python 3.11+ installed
- GPU recommended (training jobs are GPU-intensive)
- Node client dependencies installed (in `node-client/`)
- Coordinator URL (default: https://aiforge-backend.fly.dev)

## Usage

1. **Configure Training Node**:
   - Enter node name
   - Set coordinator URL
   - Configure max concurrent training jobs (recommended: 1)
   - Enable GPU (required for training)
   - Select training framework (HuggingFace/PyTorch)
   - Set storage path for datasets

2. **Start Node**:
   - Click "Start Training Node"
   - Node will automatically:
     - Detect OS
     - Detect GPU resources
     - Register with coordinator as training node
     - Start polling for training jobs only

3. **Monitor Training**:
   - View active training jobs
   - Monitor GPU usage and memory
   - Track training progress (epochs, loss, etc.)
   - View training history
   - Read training logs

## Requirements

- **Windows**: Python 3.11+, NVIDIA GPU (recommended)
- **macOS**: Python 3.11+, GPU (optional but recommended)
- **Linux**: Python 3.11+, NVIDIA GPU (recommended)

## Project Structure

```
app_training/
├── main.js          # Electron main process
├── preload.js       # Preload script (IPC bridge)
├── renderer.js      # Training UI logic
├── index.html       # Training-focused UI
├── styles.css       # Styles
├── package.json     # Dependencies and build config
└── node-client/     # Training-only Python client
    └── src/
        ├── main.py              # Registers as training node
        ├── training_executor.py # Only handles training jobs
        ├── training_handler.py  # Training logic
        ├── coordinator_client.py
        ├── resource_monitor.py
        ├── ipfs_client.py
        └── docker_manager.py
```

## Development

The app uses:
- **Electron**: Desktop app framework
- **IPC**: Communication between main and renderer processes
- **Python Shell**: Runs the training node client Python script

## Building for Production

1. Update version in `package.json`
2. Add icons to `assets/` folder:
   - `icon.ico` (Windows)
   - `icon.icns` (macOS)
   - `icon.png` (Linux)
3. Run build command for your platform
4. Installers will be in `dist/` folder

## Troubleshooting

### Node won't start
- Check Python is installed and in PATH
- Verify node-client dependencies are installed
- Check coordinator URL is correct

### No training jobs received
- Verify node is registered (check Node ID)
- Check coordinator has training jobs available
- Verify GPU is enabled (training requires GPU)
- Ensure node_type is set to "training"

### Training jobs fail
- Check GPU drivers are installed
- Verify sufficient GPU memory
- Check training dataset is accessible
- Review training logs for errors

## License

MIT

