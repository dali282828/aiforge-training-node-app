import os
import tempfile
from typing import Dict, Any, Optional
from src.config import config

# Try to import docker, make it optional
try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None

class DockerManager:
    def __init__(self):
        if not DOCKER_AVAILABLE:
            print("Docker module not available. Docker features will be disabled.")
            self.client = None
            return
        
        try:
            self.client = docker.from_env()
        except Exception as e:
            print(f"Failed to connect to Docker: {e}")
            self.client = None
    
    def is_available(self) -> bool:
        """Check if Docker is available"""
        return self.client is not None
    
    def create_job_container(self, job_config: Dict[str, Any], work_dir: str) -> Optional[str]:
        """Create and start a Docker container for a job"""
        if not self.client:
            return None
        
        try:
            env_vars = job_config.get("environment", {})
            env_vars.update({
                "JOB_ID": job_config.get("job_id"),
                "WORK_DIR": work_dir
            })
            
            container = self.client.containers.run(
                image=job_config.get("image", "python:3.11"),
                command=job_config.get("command", ["python", "-c", "print('Hello from container')"]),
                environment=env_vars,
                volumes={
                    work_dir: {"bind": "/workspace", "mode": "rw"}
                },
                network=config.DOCKER_NETWORK,
                detach=True,
                remove=False,
                mem_limit=job_config.get("memory_limit"),
                cpu_quota=int(job_config.get("cpu_limit", 1) * 100000) if job_config.get("cpu_limit") else None,
                gpus=job_config.get("gpus") if config.GPU_ENABLED else None
            )
            
            return container.id
        except Exception as e:
            print(f"Failed to create container: {e}")
            return None
    
    def get_container_logs(self, container_id: str) -> str:
        """Get logs from a container"""
        if not self.client:
            return ""
        
        try:
            container = self.client.containers.get(container_id)
            return container.logs().decode('utf-8')
        except Exception as e:
            print(f"Failed to get logs: {e}")
            return ""
    
    def stop_container(self, container_id: str):
        """Stop and remove a container"""
        if not self.client:
            return
        
        try:
            container = self.client.containers.get(container_id)
            container.stop()
            container.remove()
        except Exception as e:
            print(f"Failed to stop container: {e}")
    
    def get_container_status(self, container_id: str) -> Optional[str]:
        """Get container status"""
        if not self.client:
            return None
        
        try:
            container = self.client.containers.get(container_id)
            return container.status
        except Exception as e:
            print(f"Failed to get container status: {e}")
            return None

