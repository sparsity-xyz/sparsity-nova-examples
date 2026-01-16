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
    odyn.state_save(data)   → Save encrypted state to S3 (returns state_hash)
    odyn.state_load()       → Load encrypted state from S3

Environment:
    IN_ENCLAVE=true   → Uses localhost:8080 (production TEE)
    IN_ENCLAVE=false  → Uses mock API (development)
"""

import os
import json
import requests
from typing import Dict, Any, Optional, Tuple


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
    # Encrypted State Persistence
    # =========================================================================
    
    def state_save(self, data: Any) -> dict:
        """
        Save application state to encrypted S3 storage.
        
        The data is:
          1. Serialized to JSON
          2. Encrypted with TEE's hardware-derived key (AES-GCM)
          3. Uploaded to S3
          4. Hashed with keccak256 for on-chain verification
        
        Args:
            data: JSON-serializable data to persist
            
        Returns:
            Dict with:
              - state_hash: keccak256 hash of encrypted blob
              - object_key: S3 object key
        """
        return self._call("POST", "/v1/state/save", {"data": data})

    def state_load(self) -> dict:
        """
        Load application state from encrypted S3 storage.
        
        The encrypted blob is:
          1. Downloaded from S3
          2. Decrypted with TEE's hardware-derived key
          3. Deserialized from JSON
        
        Returns:
            Dict with:
              - data: Your application state
              - state_hash: keccak256 hash of encrypted blob
        """
        return self._call("GET", "/v1/state/load")


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
