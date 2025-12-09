"""
Enclave helper class for interacting with enclaver's odyn API.

This module provides a simple interface to the odyn API running on localhost:18000
inside the enclave environment.
"""

import json
import hashlib
import requests
from typing import Dict, Any


class Enclave:
    """Wrapper for enclaver's odyn API."""
    
    def __init__(self, endpoint: str = "http://127.0.0.1:18000"):
        """
        Initialize the Enclave helper.
        
        Args:
            endpoint: The odyn API endpoint. Defaults to localhost:18000.
        """
        self.endpoint = endpoint
    
    def eth_address(self) -> str:
        """
        Get the Ethereum address from the enclave.
        
        Returns:
            The Ethereum address as a string.
        """
        res = requests.get(f"{self.endpoint}/v1/eth/address", timeout=10)
        res.raise_for_status()
        return res.json()["address"]
    
    def get_attestation(self) -> Dict[str, Any]:
        """
        Get the attestation document from the enclave.
        
        Returns:
            The attestation document as a dictionary.
        """
        res = requests.get(f"{self.endpoint}/v1/attestation", timeout=10)
        res.raise_for_status()
        return res.json()
    
    def get_random_bytes(self, count: int = 32) -> bytes:
        """
        Get random bytes from the enclave.
        
        Args:
            count: Number of random bytes to generate.
            
        Returns:
            Random bytes.
        """
        res = requests.get(f"{self.endpoint}/v1/random", timeout=10)
        res.raise_for_status()
        random_hex = res.json()["random_bytes"]
        if random_hex.startswith("0x"):
            random_hex = random_hex[2:]
        return bytes.fromhex(random_hex)[:count]
    
    def sign_message(self, data: Dict[str, Any]) -> str:
        """
        Sign a message using the enclave's key.
        
        Args:
            data: Dictionary to sign.
            
        Returns:
            Hex-encoded signature.
        """
        message = json.dumps(data, sort_keys=True, separators=(',', ':'))
        message_bytes = message.encode('utf-8')
        message_hash = hashlib.sha256(message_bytes).hexdigest()
        
        res = requests.post(
            f"{self.endpoint}/v1/eth/sign",
            json={
                "message": f"0x{message_hash}",
                "include_attestation": False
            },
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        res.raise_for_status()
        return res.json()["signature"]
    
    def get_public_key(self) -> str:
        """
        Get the public key from the enclave.
        
        Returns:
            The public key as a hex string.
        """
        res = requests.get(f"{self.endpoint}/v1/public-key", timeout=10)
        res.raise_for_status()
        return res.json()["public_key"]


if __name__ == '__main__':
    e = Enclave()
    print(f"Ethereum address: {e.eth_address()}")
    print(f"Random bytes: {e.get_random_bytes(16).hex()}")
