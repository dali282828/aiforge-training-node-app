"""
Training Executor
Handles only training/finetune job execution
"""
import os
from typing import Dict, Any
from src.config import config
from src.coordinator_client import CoordinatorClient
from src.training_handler import execute_training_job
from src.ipfs_client import IPFSClient

class TrainingExecutor:
    def __init__(self, coordinator_client: CoordinatorClient):
        self.coordinator = coordinator_client
        self.ipfs = IPFSClient()
        self.job_work_dir = config.JOB_WORK_DIR
        os.makedirs(self.job_work_dir, exist_ok=True)
    
    def execute_training_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a training/finetune job"""
        job_id = job.get("id")
        job_type = job.get("type", "finetune")
        
        if job_type not in ["finetune", "training"]:
            raise ValueError(f"Training executor only handles training jobs, got: {job_type}")
        
        print(f"Executing training job {job_id}", flush=True)
        
        work_dir = os.path.join(self.job_work_dir, f"training_{job_id}")
        os.makedirs(work_dir, exist_ok=True)
        
        return execute_training_job(self.coordinator, self.ipfs, job, work_dir, config)

