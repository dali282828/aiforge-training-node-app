import psutil
import platform
import os
from typing import Dict, Any, Optional
import subprocess
import shutil

class ResourceMonitor:
    @staticmethod
    def get_operating_system() -> str:
        """Get operating system name normalized"""
        system = platform.system().lower()
        if system == "windows":
            return "windows"
        elif system == "linux":
            return "linux"
        elif system == "darwin":
            return "macos"
        else:
            return "unknown"
    
    @staticmethod
    def get_cpu_info() -> Dict[str, Any]:
        """Get CPU information"""
        return {
            "cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "usage_percent": psutil.cpu_percent(interval=1),
            "frequency": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
        }
    
    @staticmethod
    def get_memory_info() -> Dict[str, Any]:
        """Get memory information"""
        mem = psutil.virtual_memory()
        return {
            "total": mem.total,
            "available": mem.available,
            "used": mem.used,
            "percent": mem.percent
        }
    
    @staticmethod
    def get_gpu_info() -> Optional[Dict[str, Any]]:
        """Get GPU information (NVIDIA only for now)"""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,memory.used", 
                 "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                gpus = []
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = [p.strip() for p in line.split(',')]
                        if len(parts) >= 4:
                            gpus.append({
                                "name": parts[0],
                                "memory_total_mb": int(parts[1]),
                                "memory_free_mb": int(parts[2]),
                                "memory_used_mb": int(parts[3])
                            })
                return {"devices": gpus, "count": len(gpus)} if gpus else None
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
        return None
    
    @staticmethod
    def get_disk_info() -> Dict[str, Any]:
        """Get disk information"""
        disk = psutil.disk_usage('/')
        return {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent
        }
    
    @staticmethod
    def get_resource_info() -> Dict[str, Any]:
        """Get comprehensive resource information"""
        os_name = ResourceMonitor.get_operating_system()
        
        info = {
            "cpu": ResourceMonitor.get_cpu_info(),
            "memory": ResourceMonitor.get_memory_info(),
            "disk": ResourceMonitor.get_disk_info(),
            "platform": platform.system(),
            "platform_version": platform.version(),
            "operating_system": os_name,
            "model_runner_type": None,  # Training nodes don't need model runners
            "model_runner_version": None,
        }
        
        gpu_info = ResourceMonitor.get_gpu_info()
        if gpu_info:
            info["gpu"] = gpu_info
        
        return info

