"""
Lightweight Platform Server
Runs on nodes using 5% of resources to serve platform API
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import threading
import os
import httpx
from typing import Optional
import logging
import time

logger = logging.getLogger(__name__)

class PlatformServer:
    """Lightweight FastAPI server for platform services"""
    
    def __init__(self, port: int = 8001, coordinator_url: Optional[str] = None):
        self.port = port
        self.coordinator_url = coordinator_url or os.getenv("COORDINATOR_URL", "https://aiforge-backend.fly.dev")
        self.app = FastAPI(title="AIForge Platform Node", version="0.1.0")
        self.server_thread: Optional[threading.Thread] = None
        self.running = False
        self.server_process: Optional[uvicorn.Server] = None
        
        # Add CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Register routes
        self._register_routes()
    
    def _register_routes(self):
        """Register platform API routes"""
        
        @self.app.get("/")
        async def root():
            return {
                "message": "AIForge Platform Node",
                "version": "0.1.0",
                "type": "platform_node",
                "coordinator": self.coordinator_url
            }
        
        @self.app.get("/health")
        async def health():
            return {
                "status": "healthy",
                "type": "platform_node",
                "port": self.port
            }
        
        @self.app.get("/api/health")
        async def api_health():
            """API health check"""
            capabilities = []
            
            # Check IPFS availability - test if IPFS API is accessible
            try:
                from src.ipfs_client import IPFSClient
                import requests
                ipfs = IPFSClient()
                # Check if IPFS API is accessible (even if client is None, API might work)
                try:
                    response = requests.post(f"{ipfs.ipfs_api_url}/version", timeout=2)
                    if response.status_code == 200:
                        capabilities.append("ipfs")
                except:
                    pass
            except:
                pass
            
            # Check MinIO availability (if running locally) - check both 'minio' and 'aiforge-minio'
            try:
                import subprocess
                result1 = subprocess.run(["docker", "ps", "--filter", "name=minio", "--format", "{{.Names}}"], 
                                       capture_output=True, text=True, timeout=2)
                result2 = subprocess.run(["docker", "ps", "--filter", "name=aiforge-minio", "--format", "{{.Names}}"], 
                                       capture_output=True, text=True, timeout=2)
                if (result1.returncode == 0 and result1.stdout.strip()) or (result2.returncode == 0 and result2.stdout.strip()):
                    capabilities.append("minio")
            except:
                pass
            
            # Check Redis availability
            try:
                import redis
                try:
                    r = redis.Redis(host='localhost', port=6379, socket_connect_timeout=1)
                    r.ping()
                    capabilities.append("redis")
                except:
                    # Try checking if Redis Docker container is running (check both 'redis' and 'aiforge-redis')
                    import subprocess
                    result1 = subprocess.run(["docker", "ps", "--filter", "name=redis", "--format", "{{.Names}}"], 
                                           capture_output=True, text=True, timeout=2)
                    result2 = subprocess.run(["docker", "ps", "--filter", "name=aiforge-redis", "--format", "{{.Names}}"], 
                                           capture_output=True, text=True, timeout=2)
                    if (result1.returncode == 0 and result1.stdout.strip()) or (result2.returncode == 0 and result2.stdout.strip()):
                        capabilities.append("redis")
            except:
                pass
            
            return {
                "status": "ok", 
                "service": "platform_node",
                "capabilities": capabilities
            }
        
        # ========== IPFS Endpoints ==========
        
        @self.app.post("/api/ipfs/upload")
        async def ipfs_upload(request: Request):
            """Upload data to IPFS via this worker node"""
            try:
                import base64
                import requests
                import tempfile
                import os
                
                body = await request.json()
                data_b64 = body.get("data")
                if not data_b64:
                    raise HTTPException(status_code=400, detail="Missing 'data' field")
                
                # Decode base64 data
                data = base64.b64decode(data_b64)
                
                # Try to use IPFS HTTP API directly (works even if ipfshttpclient fails)
                # IPFS HTTP API endpoint: http://localhost:5001/api/v0/add
                try:
                    # Save to temp file
                    with tempfile.NamedTemporaryFile(delete=False) as f:
                        f.write(data)
                        temp_path = f.name
                    
                    try:
                        # Upload via IPFS HTTP API
                        with open(temp_path, 'rb') as f:
                            files = {'file': f}
                            response = requests.post(
                                'http://localhost:5001/api/v0/add',
                                files=files,
                                timeout=60
                            )
                            response.raise_for_status()
                            result = response.json()
                            cid = result.get('Hash', '')
                        
                        if not cid:
                            raise HTTPException(status_code=500, detail="Failed to get CID from IPFS")
                        
                        # Try to pin (optional)
                        try:
                            requests.post(
                                f'http://localhost:5001/api/v0/pin/add?arg={cid}',
                                timeout=10
                            )
                        except:
                            pass  # Pin is optional
                        
                        gateway_url = f"http://localhost:8080/ipfs/{cid}"
                        
                        return {
                            "success": True,
                            "cid": cid,
                            "gateway_url": gateway_url
                        }
                    finally:
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)
                            
                except requests.exceptions.ConnectionError:
                    raise HTTPException(status_code=503, detail="IPFS node not available on this worker. Make sure IPFS is running on localhost:5001")
                except Exception as e:
                    logger.error(f"IPFS upload error: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail=f"Failed to upload to IPFS: {str(e)}")
                        
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error uploading to IPFS: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"IPFS upload failed: {str(e)}")
        
        @self.app.get("/api/ipfs/download/{cid}")
        async def ipfs_download(cid: str):
            """Download data from IPFS via this worker node"""
            try:
                from fastapi.responses import Response
                import requests
                
                # Try direct IPFS node API first
                try:
                    response = requests.post(
                        f'http://localhost:5001/api/v0/cat?arg={cid}',
                        timeout=60
                    )
                    response.raise_for_status()
                    return Response(content=response.content, media_type="application/octet-stream")
                except requests.exceptions.ConnectionError:
                    logger.warning("Direct IPFS node not available, trying gateway...")
                except Exception as e:
                    logger.warning(f"Direct IPFS download failed: {e}, trying gateway...")
                
                # Fallback to gateway
                gateway_url = f"http://localhost:8080/ipfs/{cid}"
                try:
                    response = requests.get(gateway_url, timeout=60)
                    response.raise_for_status()
                    return Response(content=response.content, media_type="application/octet-stream")
                except Exception as e:
                    logger.error(f"Gateway download failed: {e}")
                    raise HTTPException(status_code=500, detail=f"IPFS download failed: {str(e)}")
                
            except Exception as e:
                logger.error(f"Error downloading from IPFS: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"IPFS download failed: {str(e)}")
        
        # ========== Redis Endpoints ==========
        
        @self.app.post("/api/redis/set")
        async def redis_set(request: Request):
            """Set a key-value pair in Redis via this worker node"""
            try:
                import redis
                import json
                
                body = await request.json()
                key = body.get("key")
                value = body.get("value")
                ttl = body.get("ttl")  # Optional TTL in seconds
                
                if not key or value is None:
                    raise HTTPException(status_code=400, detail="Missing 'key' or 'value' field")
                
                # Connect to local Redis
                try:
                    r = redis.Redis(host='localhost', port=6379, decode_responses=True, socket_connect_timeout=2)
                    r.ping()
                except:
                    # Try Docker Redis (check both 'redis' and 'aiforge-redis')
                    import subprocess
                    result1 = subprocess.run(["docker", "ps", "--filter", "name=redis", "--format", "{{.Names}}"], 
                                           capture_output=True, text=True, timeout=2)
                    result2 = subprocess.run(["docker", "ps", "--filter", "name=aiforge-redis", "--format", "{{.Names}}"], 
                                           capture_output=True, text=True, timeout=2)
                    if (result1.returncode != 0 or not result1.stdout.strip()) and (result2.returncode != 0 or not result2.stdout.strip()):
                        raise HTTPException(status_code=503, detail="Redis not available on this worker")
                    # If Docker Redis exists, try connecting to it
                    r = redis.Redis(host='localhost', port=6379, decode_responses=True, socket_connect_timeout=2)
                
                # Set value
                if isinstance(value, (dict, list)):
                    value = json.dumps(value)
                
                if ttl:
                    r.setex(key, ttl, value)
                else:
                    r.set(key, value)
                
                return {"success": True, "key": key}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Redis set error: {e}")
                raise HTTPException(status_code=500, detail=f"Redis set failed: {str(e)}")
        
        @self.app.get("/api/redis/get/{key}")
        async def redis_get(key: str):
            """Get a value from Redis via this worker node"""
            try:
                import redis
                import json
                
                # Connect to local Redis
                try:
                    r = redis.Redis(host='localhost', port=6379, decode_responses=True, socket_connect_timeout=2)
                    r.ping()
                except:
                    # Try Docker Redis (check both 'redis' and 'aiforge-redis')
                    import subprocess
                    result1 = subprocess.run(["docker", "ps", "--filter", "name=redis", "--format", "{{.Names}}"], 
                                           capture_output=True, text=True, timeout=2)
                    result2 = subprocess.run(["docker", "ps", "--filter", "name=aiforge-redis", "--format", "{{.Names}}"], 
                                           capture_output=True, text=True, timeout=2)
                    if (result1.returncode != 0 or not result1.stdout.strip()) and (result2.returncode != 0 or not result2.stdout.strip()):
                        raise HTTPException(status_code=503, detail="Redis not available on this worker")
                    r = redis.Redis(host='localhost', port=6379, decode_responses=True, socket_connect_timeout=2)
                
                # Get value
                value = r.get(key)
                if value is None:
                    raise HTTPException(status_code=404, detail=f"Key '{key}' not found")
                
                # Try to parse as JSON, if fails return as string
                try:
                    value = json.loads(value)
                except:
                    pass
                
                return {"success": True, "key": key, "value": value}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Redis get error: {e}")
                raise HTTPException(status_code=500, detail=f"Redis get failed: {str(e)}")
        
        @self.app.delete("/api/redis/delete/{key}")
        async def redis_delete(key: str):
            """Delete a key from Redis via this worker node"""
            try:
                import redis
                
                # Connect to local Redis
                try:
                    r = redis.Redis(host='localhost', port=6379, decode_responses=True, socket_connect_timeout=2)
                    r.ping()
                except:
                    # Try Docker Redis (check both 'redis' and 'aiforge-redis')
                    import subprocess
                    result1 = subprocess.run(["docker", "ps", "--filter", "name=redis", "--format", "{{.Names}}"], 
                                           capture_output=True, text=True, timeout=2)
                    result2 = subprocess.run(["docker", "ps", "--filter", "name=aiforge-redis", "--format", "{{.Names}}"], 
                                           capture_output=True, text=True, timeout=2)
                    if (result1.returncode != 0 or not result1.stdout.strip()) and (result2.returncode != 0 or not result2.stdout.strip()):
                        raise HTTPException(status_code=503, detail="Redis not available on this worker")
                    r = redis.Redis(host='localhost', port=6379, decode_responses=True, socket_connect_timeout=2)
                
                # Delete key
                deleted = r.delete(key)
                
                return {"success": True, "key": key, "deleted": deleted > 0}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Redis delete error: {e}")
                raise HTTPException(status_code=500, detail=f"Redis delete failed: {str(e)}")
    
    def start(self):
        """Start platform server in background thread"""
        if self.running:
            print("Platform server already running", flush=True)
            return
        
        def run_server():
            config = uvicorn.Config(
                self.app,
                host="0.0.0.0",
                port=self.port,
                log_level="info",
                access_log=False  # Reduce logging overhead
            )
            self.server_process = uvicorn.Server(config)
            self.server_process.run()
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        self.running = True
        print(f"Platform server started on port {self.port}", flush=True)
        print(f"Platform service URL: http://localhost:{self.port}", flush=True)
    
    def stop(self):
        """Stop platform server"""
        if not self.running:
            return
        
        self.running = False
        if self.server_process:
            self.server_process.should_exit = True
        print("Platform server stopped", flush=True)
    
    def is_running(self) -> bool:
        """Check if server is running"""
        return self.running


