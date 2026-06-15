"""
AI Security Robot Resource Manager
Manages 1.5% resource allocation for AI Security Robot services
"""
import psutil
import os
from typing import Dict, Any

class RobotResourceManager:
    """Manages 1.5% resource allocation for AI Security Robot"""
    
    def __init__(self):
        self.cpu_limit = None
        self.memory_limit = None
        self.allocation_percent = 0.015  # 1.5%
    
    def calculate_robot_resources(self) -> Dict[str, Any]:
        """Calculate 1.5% of available resources"""
        try:
            cpu_count = psutil.cpu_count(logical=True)
            memory = psutil.virtual_memory()
            
            # Calculate 1.5% allocation
            robot_cpu = max(0.1, cpu_count * self.allocation_percent)  # Minimum 0.1 CPU
            robot_memory = int(memory.total * self.allocation_percent)  # 1.5% of RAM
            
            return {
                "cpu_cores": robot_cpu,
                "memory_bytes": robot_memory,
                "memory_mb": robot_memory / (1024 * 1024),
                "allocation_percent": self.allocation_percent,
                "cpu_count_total": cpu_count,
                "memory_total_mb": memory.total / (1024 * 1024)
            }
        except Exception as e:
            # Fallback if psutil fails
            print(f"Warning: Could not calculate robot resources: {e}", flush=True)
            return {
                "cpu_cores": 0.1,
                "memory_bytes": 256 * 1024 * 1024,  # 256 MB default
                "memory_mb": 256,
                "allocation_percent": self.allocation_percent,
                "cpu_count_total": 1,
                "memory_total_mb": 1024
            }
    
    def get_resource_limits(self) -> Dict[str, Any]:
        """Get resource limits for robot service"""
        resources = self.calculate_robot_resources()
        
        # Set environment variables for resource limits (if needed)
        os.environ["ROBOT_CPU_LIMIT"] = str(resources["cpu_cores"])
        os.environ["ROBOT_MEMORY_LIMIT"] = str(resources["memory_bytes"])
        
        return resources
