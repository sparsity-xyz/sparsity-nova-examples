"""
Enclave helper class for interacting with enclaver's odyn API.

This module provides a simple interface to the odyn API running on localhost:18000
inside the enclave environment.
"""

import json
import requests
from typing import Dict, Any, Optional, Tuple

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend


class Enclave:
    """Wrapper for enclaver's odyn API with encryption support."""
    
    def __init__(self, endpoint: str = "http://127.0.0.1:18000"):
        """
        Initialize the Enclave helper.
        
        Generates a P-384 keypair for encryption/decryption operations.
        The keypair is used for ECDH key exchange with clients.
        
        Args:
            endpoint: The odyn API endpoint. Defaults to localhost:18000.
        """
        self.endpoint = endpoint
        
        # Generate P-384 keypair for encryption (separate from ETH signing key)
        # This key is used for ECDH key exchange with clients
        self._encryption_private_key = ec.generate_private_key(ec.SECP384R1(), default_backend())
        self._encryption_public_key = self._encryption_private_key.public_key()
    
    def eth_address(self) -> str:
        """
        Get the Ethereum address from the enclave.
        
        Returns:
            The Ethereum address as a string.
        """
        res = requests.get(f"{self.endpoint}/v1/eth/address", timeout=10)
        res.raise_for_status()
        return res.json()["address"]
    
    def get_attestation(self, user_data: Optional[Dict[str, Any]] = None) -> str:
        """
        Get the attestation document from the enclave.
        
        The odyn API returns CBOR-encoded attestation document as binary data.
        We base64-encode it for JSON transport.
        
        Args:
            user_data: Optional dict with custom fields to embed in attestation.
                The enclave will automatically add 'eth_addr' to this dict.
                If None, the attestation will contain only {"eth_addr": "0x..."}.

        Returns:
            Base64-encoded CBOR attestation document string.
            The user_data field in the attestation will be a JSON dict
            containing eth_addr and any custom fields provided.
        """
        import base64
        
        # Get the encryption public key in PEM format for attestation
        encryption_pub_key_pem = self._encryption_public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        
        payload = {
            "nonce": "",
            "public_key": encryption_pub_key_pem,
        }
        
        # If user_data dict is provided, include it (enclave will add eth_addr)
        if user_data is not None:
            payload["user_data"] = user_data
        
        res = requests.post(
            f"{self.endpoint}/v1/attestation",
            json=payload,
            timeout=10
        )
        res.raise_for_status()
        
        # Response is CBOR binary, base64 encode it for JSON transport
        attestation_cbor = res.content
        return base64.b64encode(attestation_cbor).decode('utf-8')
    
    def get_encryption_public_key_der(self) -> bytes:
        """
        Get the encryption public key in DER format.
        
        Returns:
            DER-encoded P-384 public key bytes.
        """
        return self._encryption_public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
    
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
        # Remove 0x prefix if present
        if random_hex.startswith("0x"):
            random_hex = random_hex[2:]
        return bytes.fromhex(random_hex)[:count]
    
    def sign_message(self, data: Dict[str, Any]) -> str:
        """Sign a dict payload by canonical JSON then /v1/eth/sign (EIP-191 prefix inside enclaver)."""
        message = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return self.sign_data(message)

    def sign_data(self, data: str) -> str:
        """
        Sign plain text data using enclaver's /v1/eth/sign (EIP-191 inside enclaver).
        Returns hex signature without 0x prefix for verifier compatibility.
        """
        res = requests.post(
            f"{self.endpoint}/v1/eth/sign",
            json={
                "message": data,
                "include_attestation": False
            },
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        res.raise_for_status()
        sig = res.json()["signature"]
        return sig[2:] if sig.startswith("0x") else sig
    
    def get_public_key(self) -> str:
        """
        Get the public key from the enclave.
        
        Returns:
            The public key as a hex string.
        """
        res = requests.get(f"{self.endpoint}/v1/public-key", timeout=10)
        res.raise_for_status()
        return res.json()["public_key"]
    
    def get_public_key_der(self) -> bytes:
        """
        Get the public key from the enclave in DER format.
        
        Returns:
            The public key as DER-encoded bytes.
        """
        pub_key_hex = self.get_public_key()
        # Remove 0x prefix if present
        if pub_key_hex.startswith("0x"):
            pub_key_hex = pub_key_hex[2:]
        return bytes.fromhex(pub_key_hex)
    
    def _derive_shared_key(self, peer_public_key_der: bytes) -> bytes:
        """
        Derive a shared AES key using ECDH + HKDF.
        
        Args:
            peer_public_key_der: Peer's public key in DER format
            
        Returns:
            32-byte AES key
        """
        peer_public_key = serialization.load_der_public_key(
            peer_public_key_der, backend=default_backend()
        )
        shared_key = self._encryption_private_key.exchange(ec.ECDH(), peer_public_key)
        aes_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"encryption data"
        ).derive(shared_key)
        return aes_key
    
    def decrypt_data(self, nonce_hex: str, client_public_key_hex: str, 
                     encrypted_data_hex: str) -> str:
        """
        Decrypt data encrypted by a client using ECDH.
        
        Args:
            nonce_hex: 32-byte nonce in hex
            client_public_key_hex: Client's ephemeral public key (DER format, hex)
            encrypted_data_hex: AES-GCM encrypted data (hex)
            
        Returns:
            Decrypted plaintext string
        """
        nonce = bytes.fromhex(nonce_hex)
        client_public_key_der = bytes.fromhex(client_public_key_hex)
        encrypted_data = bytes.fromhex(encrypted_data_hex)
        
        # Derive shared key
        aes_key = self._derive_shared_key(client_public_key_der)
        
        # Decrypt using AES-GCM
        aesgcm = AESGCM(aes_key)
        plaintext = aesgcm.decrypt(nonce, encrypted_data, None)
        
        return plaintext.decode('utf-8')
    
    def encrypt_data(self, data: str, client_public_key_der: bytes) -> Tuple[str, str, str]:
        """
        Encrypt data to send back to the client.
        
        Args:
            data: Plaintext string to encrypt
            client_public_key_der: Client's public key in DER format
            
        Returns:
            Tuple of (encrypted data hex, our public key hex, response nonce hex)
        """
        # Derive shared key
        aes_key = self._derive_shared_key(client_public_key_der)
        
        # Encode data
        plaintext = data.encode('utf-8')
        
        # Generate new nonce for response
        response_nonce = self.get_random_bytes(32)
        
        # Encrypt using AES-GCM
        aesgcm = AESGCM(aes_key)
        ciphertext = aesgcm.encrypt(response_nonce, plaintext, None)
        
        # Get our public key in DER format (same as in attestation)
        our_public_key_der = self._encryption_public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        return ciphertext.hex(), our_public_key_der.hex(), response_nonce.hex()


if __name__ == '__main__':
    # Test the enclave helper
    e = Enclave()
    print(f"Ethereum address: {e.eth_address()}")
    print(f"Random bytes: {e.get_random_bytes(16).hex()}")
    print(f"Attestation: {e.get_attestation()}")
