"""
=============================================================================
Odyn SDK (odyn.py)
=============================================================================

Platform-provided interface to TEE (Trusted Execution Environment) services.

┌─────────────────────────────────────────────────────────────────────────────┐
│  DO NOT MODIFY THIS FILE                                                    │
│  This is the standard SDK provided by Nova Platform.                        │
└─────────────────────────────────────────────────────────────────────────────┘

Available Methods:
    odyn.eth_address()      → Get TEE's Ethereum address
    odyn.get_random_bytes() → Get 32 bytes from hardware RNG
    odyn.get_attestation()  → Get Nitro attestation document (CBOR)
    odyn.sign_tx(tx)        → Sign an Ethereum transaction
    
    # S3 Storage (via Enclaver internal API)
    odyn.s3_put(key, value) → Store data in S3 storage
    odyn.s3_get(key)        → Retrieve data from S3 storage
    odyn.s3_delete(key)     → Delete data from S3 storage
    odyn.s3_list(prefix)    → List keys in S3 storage

Environment:
    IN_ENCLAVE=true   → Uses localhost:8080 (production TEE)
    IN_ENCLAVE=false  → Uses mock API (development)
"""

import os
import json
import requests
from typing import Dict, Any, Optional, Tuple, List
import base64


class Odyn:
    """
    Wrapper for enclaver's Odyn API.
    
    Automatically detects environment via IN_ENCLAVE env var:
      - IN_ENCLAVE=true  → Production (localhost:8080)
      - IN_ENCLAVE=false → Development (mock API)
    """
    
    # Mock API for local development (when not running in TEE)
    DEFAULT_MOCK_ODYN_API = "http://odyn.sparsity.cloud:8080"
    
    def __init__(self, endpoint: Optional[str] = None):
        """
        Initialize the Odyn helper.
        
        Args:
            endpoint: Override the API endpoint. If None, auto-detects
                      based on IN_ENCLAVE environment variable.
        """
        if endpoint:
            self.endpoint = endpoint
        else:
            # IN_ENCLAVE is set by the Dockerfile/enclaver runtime
            is_enclave = os.getenv("IN_ENCLAVE", "False").lower() == "true"
            self.endpoint = "http://localhost:8080" if is_enclave else self.DEFAULT_MOCK_ODYN_API

    def _call(self, method: str, path: str, payload: Any = None) -> Any:
        """Internal helper for making API calls."""
        url = f"{self.endpoint}{path}"
        if method.upper() == "POST":
            res = requests.post(url, json=payload, timeout=10)
        else:
            res = requests.get(url, timeout=10)
        res.raise_for_status()
        return res.json()

    # =========================================================================
    # Identity & Signing
    # =========================================================================
    
    def eth_address(self) -> str:
        """
        Get the TEE's Ethereum address.
        
        This address is derived from a hardware-seeded private key
        that never leaves the enclave.
        
        Returns:
            Ethereum address as hex string (e.g., "0x1234...")
        """
        return self._call("GET", "/v1/eth/address")["address"]

    def sign_tx(self, tx: dict) -> dict:
        """
        Sign an Ethereum transaction.
        
        Args:
            tx: Transaction object (to, value, data, nonce, etc.)
            
        Returns:
            Dict with raw_transaction, transaction_hash, signature
        """
        return self._call("POST", "/v1/eth/sign-tx", {"payload": tx})

    # =========================================================================
    # Randomness & Attestation
    # =========================================================================
    
    def get_random_bytes(self) -> bytes:
        """
        Get 32 random bytes from the hardware RNG (Nitro NSM).
        
        Returns:
            32 bytes of cryptographically secure random data
        """
        res_json = self._call("GET", "/v1/random")
        random_hex = res_json["random_bytes"]
        if random_hex.startswith("0x"):
            random_hex = random_hex[2:]
        return bytes.fromhex(random_hex)

    def get_attestation(self, nonce: Optional[str] = "") -> bytes:
        """
        Get a Nitro attestation document.
        
        The attestation proves this code is running in a genuine
        AWS Nitro Enclave with specific PCR measurements.
        
        Args:
            nonce: Optional nonce to include in attestation
            
        Returns:
            CBOR-encoded attestation document
        """
        url = f"{self.endpoint}/v1/attestation"
        res = requests.post(url, json={"nonce": nonce}, timeout=10)
        res.raise_for_status()
        return res.content

    # =========================================================================
    # S3 Storage (via Enclaver internal API)
    # =========================================================================
    
    def s3_put(self, key: str, value: bytes) -> bool:
        """
        Store data in S3 storage.
        
        The data is stored under the app's configured S3 prefix.
        Key is automatically scoped to prevent access to other apps' data.
        
        Args:
            key: Storage key (e.g., "state.json", "data/user_123.bin")
            value: Binary data to store
            
        Returns:
            True if successful
        """
        payload = {"key": key, "value": base64.b64encode(value).decode()}
        res = requests.post(f"{self.endpoint}/v1/s3/put", json=payload, timeout=30)
        res.raise_for_status()
        return res.json().get("success", False)

    def s3_get(self, key: str) -> Optional[bytes]:
        """
        Retrieve data from S3 storage.
        
        Args:
            key: Storage key to retrieve
            
        Returns:
            Binary data if found, None if key doesn't exist
        """
        res = requests.post(f"{self.endpoint}/v1/s3/get", json={"key": key}, timeout=30)
        if res.status_code == 404:
            return None
        res.raise_for_status()
        return base64.b64decode(res.json()["value"])

    def s3_delete(self, key: str) -> bool:
        """
        Delete data from S3 storage.
        
        Args:
            key: Storage key to delete
            
        Returns:
            True if successful
        """
        res = requests.post(f"{self.endpoint}/v1/s3/delete", json={"key": key}, timeout=30)
        res.raise_for_status()
        return res.json().get("success", False)

    def s3_list(self, prefix: str = "") -> List[str]:
        """
        List keys in S3 storage.
        
        Args:
            prefix: Optional prefix to filter keys (e.g., "data/")
            
        Returns:
            List of matching keys
        """
        res = requests.post(f"{self.endpoint}/v1/s3/list", json={"prefix": prefix}, timeout=30)
        res.raise_for_status()
        return res.json().get("keys", [])
    
    # =========================================================================
    # Convenience Methods (JSON state helpers)
    # =========================================================================
    
    def save_state(self, data: Any, key: str = "state.json") -> bool:
        """
        Convenience method to save JSON-serializable state to S3.
        
        Args:
            data: JSON-serializable data to persist
            key: Storage key (default: "state.json")
            
        Returns:
            True if successful
        """
        json_bytes = json.dumps(data).encode('utf-8')
        return self.s3_put(key, json_bytes)
    
    def load_state(self, key: str = "state.json") -> Optional[Any]:
        """
        Convenience method to load JSON state from S3.
        
        Args:
            key: Storage key (default: "state.json")
            
        Returns:
            Parsed JSON data, or None if key doesn't exist
        """
        data = self.s3_get(key)
        if data is None:
            return None
        return json.loads(data.decode('utf-8'))


# =============================================================================
# Quick Test (run directly: python odyn.py)
# =============================================================================
if __name__ == "__main__":
    o = Odyn()
    try:
        print(f"Testing Odyn at {o.endpoint}")
        print(f"TEE Address: {o.eth_address()}")
    except Exception as e:
        print(f"Could not connect to Odyn: {e}")

