"""
Training Job Handler
Handles training/finetune job execution
"""
import os
import json
import subprocess
import time
from typing import Dict, Any

def execute_training_job(coordinator, ipfs_client, job: Dict[str, Any], work_dir: str, config) -> Dict[str, Any]:
    """Execute a training/finetune job"""
    job_id = job.get("id")
    job_config = job.get("config", {})
    
    print(f"Executing training job {job_id}", flush=True)
    
    try:
        # Update status to running
        coordinator.update_job_status(job_id, "running", progress=0.0)
        
        # Extract training configuration
        base_model = job_config.get("base_model")
        dataset_cid = job_config.get("dataset_cid")
        dataset_path = job_config.get("dataset_path")
        training_framework = job_config.get("framework", "huggingface")
        
        # Hyperparameters
        hyperparams = job_config.get("hyperparameters", {})
        learning_rate = hyperparams.get("learning_rate", 2e-5)
        num_epochs = hyperparams.get("num_epochs", 3)
        batch_size = hyperparams.get("batch_size", 4)
        output_model_name = job_config.get("output_model_name", f"finetuned-{base_model}")
        
        print(f"Training configuration:", flush=True)
        print(f"  Base model: {base_model}", flush=True)
        print(f"  Framework: {training_framework}", flush=True)
        print(f"  Epochs: {num_epochs}, LR: {learning_rate}, Batch size: {batch_size}", flush=True)
        
        # Download base model if it's an IPFS CID
        model_dir = os.path.join(work_dir, "model")
        os.makedirs(model_dir, exist_ok=True)
        
        if base_model and base_model.startswith("Qm"):
            print(f"Downloading base model from IPFS: {base_model}", flush=True)
            if not ipfs_client.download_file(base_model, os.path.join(model_dir, "model")):
                raise Exception(f"Failed to download base model from IPFS: {base_model}")
            coordinator.update_job_status(job_id, "running", progress=0.1)
        else:
            print(f"Using model name: {base_model}", flush=True)
        
        # Download training dataset
        dataset_dir = os.path.join(work_dir, "dataset")
        os.makedirs(dataset_dir, exist_ok=True)
        
        dataset_file = None
        if dataset_cid:
            print(f"Downloading dataset from IPFS: {dataset_cid}", flush=True)
            dataset_file = os.path.join(dataset_dir, "dataset.json")
            if not ipfs_client.download_file(dataset_cid, dataset_file):
                raise Exception(f"Failed to download dataset from IPFS: {dataset_cid}")
            coordinator.update_job_status(job_id, "running", progress=0.2)
        elif dataset_path:
            print(f"Using dataset path: {dataset_path}", flush=True)
            dataset_file = dataset_path
        else:
            raise Exception("No dataset provided (dataset_cid or dataset_path required)")
        
        # Prepare training script
        training_script = prepare_training_script(
            work_dir=work_dir,
            framework=training_framework,
            base_model=base_model,
            dataset_path=dataset_file,
            output_dir=os.path.join(work_dir, "output"),
            hyperparams=hyperparams
        )
        
        coordinator.update_job_status(job_id, "running", progress=0.3)
        
        # Execute training
        print(f"Starting training...", flush=True)
        training_result = run_training(
            training_script=training_script,
            work_dir=work_dir,
            framework=training_framework,
            gpus=job.get("gpus", 0),
            config=config,
            coordinator=coordinator,
            job_id=job_id,
            num_epochs=num_epochs
        )
        
        coordinator.update_job_status(job_id, "running", progress=0.7)
        
        # Upload trained model to IPFS
        output_dir = os.path.join(work_dir, "output")
        if os.path.exists(output_dir):
            print(f"Uploading trained model to IPFS...", flush=True)
            model_files = []
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    if file.endswith(('.safetensors', '.bin', '.pt', '.pth', '.onnx')):
                        model_files.append(os.path.join(root, file))
            
            if model_files:
                main_model_file = model_files[0]
                output_cid = ipfs_client.upload_file(main_model_file)
                if output_cid:
                    print(f"Model uploaded to IPFS: {output_cid}", flush=True)
                else:
                    raise Exception("Failed to upload model to IPFS")
            else:
                raise Exception("No model files found in output directory")
        else:
            raise Exception("Training output directory not found")
        
        coordinator.update_job_status(job_id, "running", progress=0.9)
        
        # Prepare result
        result = {
            "output_model_cid": output_cid,
            "output_model_name": output_model_name,
            "training_metrics": training_result.get("metrics", {}),
            "framework": training_framework,
            "hyperparameters": hyperparams,
            "training_time": training_result.get("training_time", 0)
        }
        
        print(f"Training completed successfully. Model CID: {output_cid}", flush=True)
        coordinator.complete_job(job_id, result, output_cid)
        
        return result
        
    except Exception as e:
        error_msg = str(e)
        print(f"Training job {job_id} failed: {error_msg}", flush=True)
        coordinator.update_job_status(job_id, "failed", error=error_msg)
        raise

def prepare_training_script(work_dir: str, framework: str, base_model: str, 
                           dataset_path: str, output_dir: str, hyperparams: dict) -> str:
    """Prepare training script based on framework"""
    script_path = os.path.join(work_dir, "train.py")
    
    if framework == "huggingface":
        script_content = f'''#!/usr/bin/env python3
import json
import os
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer
from datasets import load_dataset
import torch

model_name = "{base_model}"
print(f"Loading model: {{model_name}}")
model = AutoModelForCausalLM.from_pretrained(model_name)
tokenizer = AutoTokenizer.from_pretrained(model_name)

if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

print(f"Loading dataset: {dataset_path}")
dataset = load_dataset("json", data_files="{dataset_path}", split="train")

def tokenize_function(examples):
    return tokenizer(examples["text"], truncation=True, padding="max_length", max_length=512)

tokenized_dataset = dataset.map(tokenize_function, batched=True)

training_args = TrainingArguments(
    output_dir="{output_dir}",
    num_train_epochs={hyperparams.get("num_epochs", 3)},
    per_device_train_batch_size={hyperparams.get("batch_size", 4)},
    learning_rate={hyperparams.get("learning_rate", 2e-5)},
    save_strategy="epoch",
    logging_steps=10,
    remove_unused_columns=False,
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_dataset,
)

print("Starting training...")
trainer.train()

print(f"Saving model to {{output_dir}}")
trainer.save_model()
tokenizer.save_pretrained(output_dir)

print("Training completed!")
'''
    else:
        script_content = f'''#!/usr/bin/env python3
# Generic training script for {framework}
print("Training script for {framework}")
print("Base model: {base_model}")
print("Dataset: {dataset_path}")
print("Output: {output_dir}")
'''
    
    with open(script_path, "w") as f:
        f.write(script_content)
    
    os.chmod(script_path, 0o755)
    return script_path

def run_training(training_script: str, work_dir: str, framework: str, gpus: int, config, 
                coordinator, job_id: str, num_epochs: int) -> dict:
    """Execute training script with progress updates"""
    start_time = time.time()
    
    cmd = ["python", training_script]
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = ",".join(map(str, range(gpus))) if gpus > 0 else ""
    
    try:
        process = subprocess.Popen(
            cmd,
            cwd=work_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        stdout_lines = []
        current_epoch = 0
        
        for line in process.stdout:
            stdout_lines.append(line)
            print(line, end='', flush=True)
            
            # Parse epoch progress
            if "epoch" in line.lower() and "/" in line:
                try:
                    parts = line.lower().split("epoch")[1].strip().split("/")[0].strip()
                    if parts.isdigit():
                        current_epoch = int(parts)
                        progress = (current_epoch / num_epochs) * 100
                        coordinator.update_job_status(job_id, "running", progress=min(progress, 0.7))
                        print(f"Epoch {current_epoch}/{num_epochs}", flush=True)
                except:
                    pass
            
            # Parse loss
            if "loss" in line.lower() and "=" in line:
                try:
                    loss_part = line.split("loss")[1].split("=")[1].strip().split()[0]
                    loss_value = float(loss_part)
                    print(f"Loss: {loss_value}", flush=True)
                except:
                    pass
        
        process.wait(timeout=config.JOB_TIMEOUT)
        
        if process.returncode != 0:
            raise Exception(f"Training failed with return code {process.returncode}")
        
        metrics = {}
        for line in stdout_lines:
            if "loss" in line.lower():
                pass
        
        training_time = time.time() - start_time
        
        return {
            "metrics": metrics,
            "training_time": training_time,
            "stdout": "\n".join(stdout_lines)
        }
    except subprocess.TimeoutExpired:
        process.kill()
        raise Exception(f"Training timed out after {config.JOB_TIMEOUT} seconds")
    except Exception as e:
        raise Exception(f"Training execution failed: {str(e)}")

