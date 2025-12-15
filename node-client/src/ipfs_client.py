import requests
from typing import Optional
from src.config import config

# Try to import ipfshttpclient, make it optional
try:
    import ipfshttpclient
    IPFS_AVAILABLE = True
except ImportError:
    IPFS_AVAILABLE = False
    ipfshttpclient = None

class IPFSClient:
    def __init__(self):
        self.client = None
        self.gateway = config.IPFS_GATEWAY
        self._connect()
    
    def _connect(self):
        """Connect to IPFS node"""
        if not IPFS_AVAILABLE:
            print("IPFS client module not available. Will use gateway only.")
            self.client = None
            return
        
        try:
            self.client = ipfshttpclient.connect(f'/ip4/{config.IPFS_HOST}/tcp/{config.IPFS_PORT}')
        except Exception as e:
            print(f"Warning: Failed to connect to IPFS node: {e}")
            print("Will use IPFS gateway for downloads")
            self.client = None
    
    def download_file(self, cid: str, output_path: str) -> bool:
        """Download file from IPFS by CID"""
        if self.client:
            try:
                self.client.get(cid, output_path)
                return True
            except Exception as e:
                print(f"Direct IPFS download failed: {e}, trying gateway...")
        
        try:
            gateway_url = f"{self.gateway}/ipfs/{cid}"
            response = requests.get(gateway_url, stream=True, timeout=300)
            response.raise_for_status()
            
            import os
            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            print(f"Gateway download failed: {e}")
            return False
    
    def upload_file(self, file_path: str) -> Optional[str]:
        """Upload file to IPFS and return CID"""
        if not self.client:
            print("IPFS client not available, cannot upload")
            return None
        
        try:
            result = self.client.add(file_path)
            if isinstance(result, dict):
                return result.get('Hash')
            return result
        except Exception as e:
            print(f"Failed to upload to IPFS: {e}")
            return None

