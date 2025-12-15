import requests
import time
import sys
import json
import threading
from typing import Optional, Dict, Any, Callable
from src.config import config
from src.resource_monitor import ResourceMonitor

# Force unbuffered output for Electron app
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

class CoordinatorClient:
    def __init__(self):
        self.base_url = config.COORDINATOR_URL
        self.token = config.NODE_TOKEN
        self.node_id: Optional[str] = None
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # WebSocket support
        self.websocket = None
        self.websocket_thread = None
        self.websocket_connected = False
        self.websocket_enabled = True  # Can be disabled via config
        self.job_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    
    def register(self, node_info: Dict[str, Any]) -> bool:
        """Register this node with the coordinator"""
        try:
            print(f"Attempting to register with coordinator at: {self.base_url}/api/nodes/register", flush=True)
            response = self.session.post(
                f"{self.base_url}/api/nodes/register",
                json=node_info,
                timeout=30
            )
            print(f"Registration response status: {response.status_code}", flush=True)
            if response.status_code == 201:
                data = response.json()
                self.node_id = data.get("node_id")
                self.token = data.get("token") or self.token
                if self.token:
                    self.session.headers.update({"Authorization": f"Bearer {self.token}"})
                message = data.get("message", "Node registered successfully")
                print(f"{message}", flush=True)
                if self.node_id:
                    print(f"Node ID: {self.node_id}", flush=True)
                return True
            else:
                error_text = response.text
                print(f"Registration failed: {response.status_code} - {error_text}")
                return False
        except requests.exceptions.Timeout:
            print(f"ERROR: Registration request timed out after 30 seconds")
            print(f"Check if coordinator is reachable at: {self.base_url}")
            return False
        except requests.exceptions.ConnectionError as e:
            print(f"ERROR: Could not connect to coordinator at: {self.base_url}")
            print(f"Connection error: {e}")
            return False
        except Exception as e:
            import traceback
            print(f"ERROR: Error registering node: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            return False
    
    def heartbeat(self) -> bool:
        """Send heartbeat to coordinator"""
        if not self.node_id:
            return False
        
        try:
            resource_info = ResourceMonitor.get_resource_info()
            response = self.session.post(
                f"{self.base_url}/api/nodes/{self.node_id}/heartbeat",
                json={
                    "status": "active",
                    "resources": resource_info,
                    "timestamp": time.time()
                },
                timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Error sending heartbeat: {e}")
            return False
    
    def heartbeat_with_platform_info(self, platform_url: str, platform_resources: dict, capabilities: list, platform_server) -> bool:
        """Send heartbeat with platform service information"""
        if not self.node_id:
            return False
        
        try:
            resource_info = ResourceMonitor.get_resource_info()
            
            # Add platform service information
            resource_info["platform_service"] = {
                "enabled": True,
                "port": platform_server.port if platform_server else 8001,
                "resources": platform_resources,
                "url": platform_url,
                "status": "running" if (platform_server and platform_server.is_running()) else "stopped",
                "capabilities": capabilities
            }
            resource_info["platform_url"] = platform_url
            
            response = self.session.post(
                f"{self.base_url}/api/nodes/{self.node_id}/heartbeat",
                json={
                    "status": "active",
                    "resources": resource_info,
                    "timestamp": time.time()
                },
                timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Error sending heartbeat: {e}")
            return False
    
    def poll_job(self) -> Optional[Dict[str, Any]]:
        """Poll coordinator for available training jobs"""
        if not self.node_id:
            return None
        
        try:
            response = self.session.get(
                f"{self.base_url}/api/nodes/{self.node_id}/jobs/poll",
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("job"):
                    return data["job"]
            return None
        except Exception as e:
            error_str = str(e)
            error_type = type(e).__name__
            
            if any(keyword in error_str for keyword in [
                "Connection aborted", 
                "RemoteDisconnected", 
                "Connection reset", 
                "Broken pipe",
                "Remote end closed"
            ]):
                return None
            elif "Timeout" in error_type or "timeout" in error_str.lower():
                return None
            elif "Connection" in error_type or "connection" in error_str.lower():
                if not hasattr(self, '_poll_error_count'):
                    self._poll_error_count = 0
                self._poll_error_count += 1
                if self._poll_error_count % 10 == 0:
                    print(f"Warning: Connection issue while polling (logged every 10th error): {error_type}", flush=True)
                return None
            else:
                print(f"Warning: Error polling for jobs: {error_type}: {error_str}", flush=True)
                return None
    
    def update_job_status(self, job_id: str, status: str, progress: Optional[float] = None, 
                         result: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        """Update job status on coordinator"""
        if not self.node_id:
            return False
        
        try:
            if progress is None:
                if status == "failed" or status == "completed":
                    progress = 1.0
                else:
                    progress = 0.0
            
            payload = {
                "status": status,
                "progress": progress,
                "result": result,
                "error": error
            }
            response = self.session.put(
                f"{self.base_url}/api/nodes/{self.node_id}/jobs/{job_id}/status",
                json=payload,
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Error updating job status: {e}")
            return False
    
    def complete_job(self, job_id: str, result: Dict[str, Any], output_cid: Optional[str] = None):
        """Mark job as complete"""
        if not self.node_id:
            return False
        
        try:
            payload = {
                "status": "completed",
                "result": result,
                "output_cid": output_cid
            }
            response = self.session.post(
                f"{self.base_url}/api/nodes/{self.node_id}/jobs/{job_id}/complete",
                json=payload,
                timeout=30
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Error completing job: {e}")
            return False
    
    def set_job_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Set callback function to handle jobs received via WebSocket"""
        self.job_callback = callback
    
    def connect_websocket(self) -> bool:
        """Connect to backend via WebSocket for instant job assignment"""
        if not self.websocket_enabled or not self.node_id:
            return False
        
        try:
            import websockets
            import asyncio
            
            # Convert HTTP URL to WebSocket URL
            ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
            # Backend now accepts node_id string directly
            ws_endpoint = f"{ws_url}/api/core/ws/jobs/{self.node_id}"
            
            # Add auth header if token exists
            # Use query parameter for authentication (more compatible)
            if self.token:
                separator = "&" if "?" in ws_endpoint else "?"
                ws_endpoint = f"{ws_endpoint}{separator}token={self.token}"
            
            print(f"Connecting to WebSocket: {ws_endpoint}", flush=True)
            
            async def websocket_loop():
                """WebSocket connection loop"""
                ws = None
                try:
                    # Connect without headers (using query param for auth)
                    ws = await websockets.connect(ws_endpoint)
                    self.websocket = ws
                    self.websocket_connected = True
                    print("WebSocket connected - instant job assignment enabled", flush=True)
                    
                    # Send ready message
                    await ws.send(json.dumps({"type": "ready"}))
                    
                    # Listen for messages
                    while self.websocket_connected:
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=30.0)
                            data = json.loads(message)
                            
                            if data.get("type") == "new_job":
                                job = data.get("job")
                                if job and self.job_callback:
                                    # Call callback in a thread-safe way
                                    threading.Thread(
                                        target=self.job_callback,
                                        args=(job,),
                                        daemon=True
                                    ).start()
                            
                        except asyncio.TimeoutError:
                            # Send keepalive
                            await ws.send(json.dumps({"type": "ping"}))
                            continue
                        except websockets.exceptions.ConnectionClosed:
                            print("WebSocket connection closed", flush=True)
                            break
                        except Exception as e:
                            print(f"WebSocket message error: {e}", flush=True)
                            
                except Exception as e:
                    print(f"WebSocket connection error: {e}", flush=True)
                    print("Falling back to polling mode", flush=True)
                finally:
                    self.websocket_connected = False
                    if ws:
                        try:
                            await ws.close()
                        except:
                            pass
                    self.websocket = None
            
            # Run WebSocket in background thread with its own event loop
            def run_websocket():
                try:
                    # Create new event loop for this thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(websocket_loop())
                    loop.close()
                except Exception as e:
                    print(f"WebSocket thread error: {e}", flush=True)
                    self.websocket_connected = False
            
            self.websocket_thread = threading.Thread(target=run_websocket, daemon=True)
            self.websocket_thread.start()
            
            # Wait a bit to see if connection succeeds
            time.sleep(2)
            return self.websocket_connected
            
        except ImportError:
            print("websockets library not installed, using polling only", flush=True)
            self.websocket_enabled = False
            return False
        except Exception as e:
            print(f"Failed to connect WebSocket: {e}, using polling", flush=True)
            return False
    
    def disconnect_websocket(self):
        """Disconnect WebSocket"""
        self.websocket_connected = False
        # The WebSocket thread will handle cleanup

