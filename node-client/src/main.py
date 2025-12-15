#!/usr/bin/env python3
"""
AIForge Network Training Node Client
Connects to coordinator and executes training/finetune jobs only
"""

import time
import signal
import sys
import os
import socket
import httpx
from typing import Dict, Any
from src.config import config
from src.coordinator_client import CoordinatorClient
from src.resource_monitor import ResourceMonitor
from src.training_executor import TrainingExecutor
from src.platform_server import PlatformServer
from src.platform_resource_manager import PlatformResourceManager

# Force unbuffered output for Electron app
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

class TrainingNodeClient:
    def __init__(self):
        self.running = False
        self.coordinator = CoordinatorClient()
        self.executor = TrainingExecutor(self.coordinator)
        self.heartbeat_interval = 30  # seconds
        self.job_poll_interval = 10  # seconds (longer for training)
        self.last_heartbeat = 0
        
        # Initialize platform service (5% resources for platform)
        self.platform_manager = PlatformResourceManager()
        
        # Use basic platform server for training nodes
        self.platform_server = PlatformServer(port=8001, coordinator_url=config.COORDINATOR_URL)
        
        # Start platform server on node startup
        print("Initializing platform service (5% resources)...", flush=True)
        platform_resources = self.platform_manager.get_resource_limits()
        print(f"Platform allocation: {platform_resources['cpu_cores']:.2f} CPU cores, {platform_resources['memory_mb']:.2f} MB RAM", flush=True)
        self.platform_server.start()
    
    def _get_public_ip(self) -> str:
        """Get node's public IP address"""
        try:
            # Try multiple services for reliability
            services = [
                "https://api.ipify.org",
                "https://ifconfig.me/ip",
                "https://icanhazip.com",
                "https://checkip.amazonaws.com"
            ]
            
            for service in services:
                try:
                    response = httpx.get(service, timeout=3.0)
                    if response.status_code == 200:
                        ip = response.text.strip()
                        # Validate IP address format
                        socket.inet_aton(ip)
                        return ip
                except:
                    continue
        except Exception as e:
            print(f"Warning: Could not detect public IP: {e}", flush=True)
        
        return None
    
    def _get_platform_url(self) -> str:
        """Get platform URL - prefer manual config, then public IP, fallback to localhost"""
        port = self.platform_server.port
        
        # Priority 1: Manual configuration (for production deployments)
        if hasattr(config, 'PLATFORM_PUBLIC_URL') and config.PLATFORM_PUBLIC_URL:
            platform_url = config.PLATFORM_PUBLIC_URL.rstrip('/')
            print(f"Platform URL: {platform_url} (manually configured)", flush=True)
            return platform_url
        
        # Priority 2: Auto-detect public IP
        public_ip = self._get_public_ip()
        if public_ip:
            platform_url = f"http://{public_ip}:{port}"
            print(f"Platform URL: {platform_url} (public IP detected)", flush=True)
            return platform_url
        
        # Priority 3: Fallback to localhost (for local testing only)
        platform_url = f"http://localhost:{port}"
        print(f"Platform URL: {platform_url} (localhost - backend may not be able to access)", flush=True)
        print(f"  To fix: Set PLATFORM_PUBLIC_URL environment variable to your public IP/domain", flush=True)
        return platform_url
    
    def _detect_capabilities(self) -> list:
        """Detect available capabilities (Redis, IPFS, MinIO)"""
        capabilities = []
        
        # Check IPFS
        try:
            from src.ipfs_client import IPFSClient
            import requests
            ipfs = IPFSClient()
            try:
                response = requests.post(f"{ipfs.ipfs_api_url}/version", timeout=2)
                if response.status_code == 200:
                    capabilities.append("ipfs")
            except:
                pass
        except:
            pass
        
        # Check MinIO
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
        
        # Check Redis
        try:
            import redis
            try:
                r = redis.Redis(host='localhost', port=6379, socket_connect_timeout=1)
                r.ping()
                capabilities.append("redis")
            except:
                # Try checking if Redis Docker container is running
                import subprocess
                result1 = subprocess.run(["docker", "ps", "--filter", "name=redis", "--format", "{{.Names}}"], 
                                       capture_output=True, text=True, timeout=2)
                result2 = subprocess.run(["docker", "ps", "--filter", "name=aiforge-redis", "--format", "{{.Names}}"], 
                                       capture_output=True, text=True, timeout=2)
                if (result1.returncode == 0 and result1.stdout.strip()) or (result2.returncode == 0 and result2.stdout.strip()):
                    capabilities.append("redis")
        except:
            pass
        
        return capabilities
    
    def register_node(self) -> bool:
        """Register this training node with the coordinator"""
        resource_info = ResourceMonitor.get_resource_info()
        
        # Extract OS and GPU info
        operating_system = resource_info.get("operating_system", "unknown")
        gpu_info = resource_info.get("gpu", {})
        gpu_count = len(gpu_info.get("devices", [])) if isinstance(gpu_info, dict) else 0
        
        # Add platform service information (5% resources)
        platform_resources = self.platform_manager.calculate_platform_resources()
        
        # Get platform URL - try to get external IP or use localhost
        platform_url = self._get_platform_url()
        
        # Check capabilities (IPFS, MinIO, and Redis)
        capabilities = self._detect_capabilities()
        
        resource_info["platform_service"] = {
            "enabled": True,
            "port": 8001,
            "resources": platform_resources,
            "url": platform_url,
            "status": "running" if self.platform_server.is_running() else "stopped",
            "capabilities": capabilities
        }
        
        # Also add platform_url at root level for easier access
        resource_info["platform_url"] = platform_url
        
        node_info = {
            "name": config.NODE_NAME,
            "description": config.NODE_DESCRIPTION or "Training Node",
            "resources": resource_info,
            "max_concurrent_jobs": config.MAX_CONCURRENT_JOBS,
            "gpu_enabled": config.GPU_ENABLED,
            "operating_system": operating_system,
            "node_type": "training",  # Mark as training node
            "model_runner_type": None,  # Training nodes don't need model runners
            "model_runner_version": None
        }
        
        # Also add node_type to resources dict for backward compatibility
        if isinstance(node_info["resources"], dict):
            node_info["resources"]["node_type"] = "training"
        
        # Add wallet information if available
        if hasattr(config, 'WALLET_ADDRESS') and config.WALLET_ADDRESS:
            node_info["wallet_address"] = config.WALLET_ADDRESS
        if hasattr(config, 'WALLET_NETWORK') and config.WALLET_NETWORK:
            node_info["wallet_network"] = config.WALLET_NETWORK
        
        print("Starting AIForge Training Node Client...", flush=True)
        print(f"Coordinator URL: {config.COORDINATOR_URL}", flush=True)
        print(f"Node Name: {config.NODE_NAME}", flush=True)
        print(f"Registering training node '{config.NODE_NAME}' with coordinator...", flush=True)
        print(f"  OS: {operating_system}", flush=True)
        print(f"  GPU Enabled: {config.GPU_ENABLED}", flush=True)
        if gpu_count > 0:
            print(f"  GPUs Detected: {gpu_count}", flush=True)
        else:
            print(f"  GPUs Detected: None (training may be slow)", flush=True)
        print(f"  Max Concurrent Jobs: {config.MAX_CONCURRENT_JOBS}", flush=True)
        print(f"  Platform Service: Running on port {self.platform_server.port} (5% resources)", flush=True)
        if capabilities:
            print(f"  Capabilities: {', '.join(capabilities)}", flush=True)
        else:
            print(f"  Capabilities: None detected", flush=True)
        
        return self.coordinator.register(node_info)
    
    def send_heartbeat(self):
        """Send periodic heartbeat to coordinator"""
        current_time = time.time()
        if current_time - self.last_heartbeat >= self.heartbeat_interval:
            # Update platform URL in heartbeat (IP might have changed)
            platform_url = self._get_platform_url()
            platform_resources = self.platform_manager.calculate_platform_resources()
            
            # Get capabilities
            capabilities = self._detect_capabilities()
            
            # Update resource info with platform service
            resource_info = ResourceMonitor.get_resource_info()
            resource_info["platform_service"] = {
                "enabled": True,
                "port": 8001,
                "resources": platform_resources,
                "url": platform_url,
                "status": "running" if self.platform_server.is_running() else "stopped",
                "capabilities": capabilities
            }
            resource_info["platform_url"] = platform_url
            
            if self.coordinator.heartbeat_with_platform_info(platform_url, platform_resources, capabilities, self.platform_server):
                self.last_heartbeat = current_time
                print("Heartbeat sent", flush=True)
            else:
                print("Warning: Heartbeat failed", flush=True)
    
    def handle_websocket_job(self, job: Dict[str, Any]):
        """Handle job received via WebSocket"""
        job_type = job.get("type", "")
        if job_type == "finetune" or job_type == "training":
            print(f"Received training job via WebSocket: {job.get('id')}", flush=True)
            try:
                self.executor.execute_training_job(job)
            except Exception as e:
                print(f"Error executing training job: {e}", flush=True)
        else:
            print(f"Ignoring non-training job via WebSocket: {job_type}", flush=True)
    
    def process_jobs(self):
        """Poll for and process training jobs only (fallback if WebSocket not available)"""
        # Only poll if WebSocket is not connected
        if not self.coordinator.websocket_connected:
            job = self.coordinator.poll_job()
            if job:
                job_type = job.get("type", "")
                if job_type == "finetune" or job_type == "training":
                    print(f"Received training job via polling: {job.get('id')}", flush=True)
                    try:
                        self.executor.execute_training_job(job)
                    except Exception as e:
                        print(f"Error executing training job: {e}", flush=True)
                else:
                    print(f"Ignoring non-training job: {job_type}", flush=True)
    
    def run(self):
        """Main loop"""
        # Register node
        if not self.register_node():
            print("Failed to register training node. Exiting.", flush=True)
            return
        
        print("Training node registered successfully!", flush=True)
        print(f"Node ID: {self.coordinator.node_id}", flush=True)
        
        # Try to connect WebSocket for instant job assignment
        # Set callback for jobs received via WebSocket
        self.coordinator.set_job_callback(self.handle_websocket_job)
        websocket_connected = self.coordinator.connect_websocket()
        if websocket_connected:
            print("WebSocket connected - using instant job assignment", flush=True)
        else:
            print("WebSocket not available - using polling mode", flush=True)
        
        print("Node client running. Press Ctrl+C to stop.", flush=True)
        
        # Setup signal handlers
        def signal_handler(sig, frame):
            print("\nShutting down training node client...", flush=True)
            self.running = False
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        self.running = True
        
        # Main loop
        while self.running:
            try:
                # Send heartbeat
                self.send_heartbeat()
                
                # Poll for training jobs
                self.process_jobs()
                
                # Sleep before next iteration
                time.sleep(self.job_poll_interval)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error in main loop: {e}", flush=True)
                time.sleep(5)
        
        print("Training node client stopped.", flush=True)

def main():
    client = TrainingNodeClient()
    client.run()

if __name__ == "__main__":
    main()

