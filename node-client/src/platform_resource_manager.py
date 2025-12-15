"""
Platform Resource Manager
Manages 5% resource allocation for platform services
"""
import psutil
import os
from typing import Dict, Any

class PlatformResourceManager:
    """Manages 5% resource allocation for platform"""
    
    def __init__(self):
        self.cpu_limit = None
        self.memory_limit = None
        self.allocation_percent = 0.05  # 5%
    
    def calculate_platform_resources(self) -> Dict[str, Any]:
        """Calculate 5% of available resources"""
        try:
            cpu_count = psutil.cpu_count(logical=True)
            memory = psutil.virtual_memory()
            
            # Calculate 5% allocation
            platform_cpu = max(0.1, cpu_count * self.allocation_percent)  # Minimum 0.1 CPU
            platform_memory = int(memory.total * self.allocation_percent)  # 5% of RAM
            
            return {
                "cpu_cores": platform_cpu,
                "memory_bytes": platform_memory,
                "memory_mb": platform_memory / (1024 * 1024),
                "allocation_percent": self.allocation_percent,
                "cpu_count_total": cpu_count,
                "memory_total_mb": memory.total / (1024 * 1024)
            }
        except Exception as e:
            # Fallback if psutil fails
            print(f"Warning: Could not calculate platform resources: {e}", flush=True)
            return {
                "cpu_cores": 0.1,
                "memory_bytes": 512 * 1024 * 1024,  # 512 MB default
                "memory_mb": 512,
                "allocation_percent": self.allocation_percent,
                "cpu_count_total": 1,
                "memory_total_mb": 1024
            }
    
    def get_resource_limits(self) -> Dict[str, Any]:
        """Get resource limits for platform service"""
        resources = self.calculate_platform_resources()
        
        # Set environment variables for resource limits (if needed)
        os.environ["PLATFORM_CPU_LIMIT"] = str(resources["cpu_cores"])
        os.environ["PLATFORM_MEMORY_LIMIT"] = str(resources["memory_bytes"])
        
        return resources


