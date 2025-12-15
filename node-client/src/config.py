import os
from typing import Optional

# Try to use pydantic, fallback to simple config if not available
_pydantic_available = False
BaseSettings = None

try:
    try:
        from pydantic_settings import BaseSettings
        _pydantic_available = True
    except ImportError:
        try:
            from pydantic import BaseSettings
            _pydantic_available = True
        except ImportError:
            pass
except Exception:
    pass

if _pydantic_available and BaseSettings:
    # Use pydantic if available
    class NodeConfig(BaseSettings):
        # Coordinator connection
        COORDINATOR_URL: str = "https://aiforge-backend.fly.dev"
        NODE_TOKEN: Optional[str] = None
        
        # Node identification
        NODE_NAME: str = "training-node-1"
        NODE_DESCRIPTION: Optional[str] = None
        NODE_TYPE: str = "training"  # Training node type
        
        # Wallet information
        WALLET_ADDRESS: Optional[str] = None
        WALLET_NETWORK: Optional[str] = None
        
        # Resource limits
        MAX_CONCURRENT_JOBS: int = 1  # Training jobs are resource-intensive
        GPU_ENABLED: bool = True  # Training requires GPU
        CPU_LIMIT: Optional[float] = None
        
        # Docker settings
        DOCKER_NETWORK: str = "bridge"
        JOB_TIMEOUT: int = 86400  # 24 hours for training jobs
        
        # IPFS settings
        IPFS_HOST: str = "localhost"
        IPFS_PORT: int = 5001
        IPFS_GATEWAY: str = "http://localhost:8080"
        
        # Job storage
        JOB_WORK_DIR: str = "./training_jobs"
        
        # Platform service URL (optional - for manual configuration)
        # If set, this will be used instead of auto-detecting public IP
        PLATFORM_PUBLIC_URL: Optional[str] = None  # e.g., "http://your-ip:8001" or "https://your-domain.com"
        
        class Config:
            env_file = ".env"
            case_sensitive = True
    
    config = NodeConfig()
else:
    # Fallback: Simple config using environment variables
    class NodeConfig:
        def __init__(self):
            # Coordinator connection
            self.COORDINATOR_URL = os.getenv("COORDINATOR_URL", "https://aiforge-backend.fly.dev")
            self.NODE_TOKEN = os.getenv("NODE_TOKEN", None)
            
            # Node identification
            self.NODE_NAME = os.getenv("NODE_NAME", "training-node-1")
            self.NODE_DESCRIPTION = os.getenv("NODE_DESCRIPTION", None)
            self.NODE_TYPE = os.getenv("NODE_TYPE", "training")
            
            # Wallet information
            self.WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", None)
            self.WALLET_NETWORK = os.getenv("WALLET_NETWORK", None)
            
            # Resource limits
            self.MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "1"))
            self.GPU_ENABLED = os.getenv("GPU_ENABLED", "true").lower() == "true"
            cpu_limit = os.getenv("CPU_LIMIT")
            self.CPU_LIMIT = float(cpu_limit) if cpu_limit else None
            
            # Docker settings
            self.DOCKER_NETWORK = os.getenv("DOCKER_NETWORK", "bridge")
            self.JOB_TIMEOUT = int(os.getenv("JOB_TIMEOUT", "86400"))
            
            # IPFS settings
            self.IPFS_HOST = os.getenv("IPFS_HOST", "localhost")
            self.IPFS_PORT = int(os.getenv("IPFS_PORT", "5001"))
            self.IPFS_GATEWAY = os.getenv("IPFS_GATEWAY", "http://localhost:8080")
            
            # Job storage
            self.JOB_WORK_DIR = os.getenv("JOB_WORK_DIR", "./training_jobs")
            
            # Platform service URL (optional - for manual configuration)
            # If set, this will be used instead of auto-detecting public IP
            self.PLATFORM_PUBLIC_URL = os.getenv("PLATFORM_PUBLIC_URL", None)
    
    config = NodeConfig()

