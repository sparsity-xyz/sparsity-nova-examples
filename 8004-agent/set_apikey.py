#!/usr/bin/env python3
"""
Interactive script to set OpenAI API key for 8004-Agent.

This script:
1. Fetches the agent's encryption public key from /get_encryption_key
2. Encrypts the OpenAI API key using P-384 ECDH + AES-256-GCM
3. Sends the encrypted key to /set_encrypted_apikey
"""

import os
import sys
import requests
from urllib.parse import urljoin

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend


def encrypt_api_key(server_public_key_hex: str, api_key: str) -> tuple:
    """
    Encrypt the API key using the server's public key.
    
    Args:
        server_public_key_hex: Server's P-384 public key in DER format (hex)
        api_key: The OpenAI API key to encrypt
        
    Returns:
        Tuple of (nonce_hex, ephemeral_public_key_hex, encrypted_key_hex)
    """
    # Load server's public key
    server_public_key_der = bytes.fromhex(server_public_key_hex)
    server_public_key = serialization.load_der_public_key(
        server_public_key_der, backend=default_backend()
    )
    
    # Step 1: Generate an ephemeral P-384 keypair
    ephemeral_private_key = ec.generate_private_key(ec.SECP384R1(), default_backend())
    ephemeral_public_key = ephemeral_private_key.public_key()
    
    # Step 2: Perform ECDH key exchange with server's public key
    shared_key = ephemeral_private_key.exchange(ec.ECDH(), server_public_key)
    
    # Step 3: Derive AES key using HKDF-SHA256
    aes_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"encryption data"
    ).derive(shared_key)
    
    # Step 4: Generate a random 32-byte nonce
    nonce = os.urandom(32)
    
    # Step 5: Encrypt the API key using AES-256-GCM
    aesgcm = AESGCM(aes_key)
    plaintext = api_key.encode('utf-8')
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    
    # Step 6: Prepare the ephemeral public key in DER format
    ephemeral_public_key_der = ephemeral_public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    return nonce.hex(), ephemeral_public_key_der.hex(), ciphertext.hex()


def get_encryption_key(agent_url: str) -> str:
    """
    Fetch the encryption public key from the agent.
    
    Args:
        agent_url: The agent's HTTPS URL
        
    Returns:
        The server's public key in hex format
    """
    url = urljoin(agent_url.rstrip('/') + '/', 'get_encryption_key')
    print(f"\n📡 Fetching encryption key from: {url}")
    
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    
    data = response.json()
    public_key = data['public_key']
    algorithm = data.get('algorithm', 'Unknown')
    
    print(f"✅ Received public key (algorithm: {algorithm})")
    print(f"   Public key (first 64 chars): {public_key[:64]}...")
    
    return public_key


def set_encrypted_apikey(agent_url: str, nonce: str, public_key: str, encrypted_key: str) -> dict:
    """
    Send the encrypted API key to the agent.
    
    Args:
        agent_url: The agent's HTTPS URL
        nonce: The encryption nonce (hex)
        public_key: The ephemeral public key (hex)
        encrypted_key: The encrypted API key (hex)
        
    Returns:
        The response from the server
    """
    url = urljoin(agent_url.rstrip('/') + '/', 'set_encrypted_apikey')
    print(f"\n📤 Sending encrypted API key to: {url}")
    
    payload = {
        "nonce": nonce,
        "public_key": public_key,
        "encrypted_key": encrypted_key
    }
    
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    
    return response.json()


def validate_url(url: str) -> str:
    """Validate and normalize the URL."""
    url = url.strip()
    if not url:
        raise ValueError("URL cannot be empty")
    
    # Add https:// if no protocol specified
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    return url


def validate_api_key(api_key: str) -> str:
    """Validate the API key format."""
    api_key = api_key.strip()
    if not api_key:
        raise ValueError("API key cannot be empty")
    
    # OpenAI API keys typically start with sk-
    if not api_key.startswith('sk-'):
        print("⚠️  Warning: OpenAI API keys typically start with 'sk-'")
    
    return api_key


def main():
    """Main function to run the interactive script."""
    print("=" * 60)
    print("🔐 8004-Agent OpenAI API Key Setup Tool")
    print("=" * 60)
    print("\nThis tool securely sets your OpenAI API key for the agent.")
    print("The key is encrypted using P-384 ECDH + AES-256-GCM before")
    print("being sent to the agent.")
    
    # Get agent URL
    print("\n" + "-" * 40)
    agent_url = input("🌐 Enter the agent's HTTPS URL: ").strip()
    
    try:
        agent_url = validate_url(agent_url)
        print(f"   Using URL: {agent_url}")
    except ValueError as e:
        print(f"❌ Invalid URL: {e}")
        sys.exit(1)
    
    # Get OpenAI API key (with hidden input option)
    print("\n" + "-" * 40)
    try:
        import getpass
        api_key = getpass.getpass("🔑 Enter your OpenAI API key (hidden): ")
    except Exception:
        # Fallback to regular input if getpass fails
        api_key = input("🔑 Enter your OpenAI API key: ")
    
    try:
        api_key = validate_api_key(api_key)
    except ValueError as e:
        print(f"❌ Invalid API key: {e}")
        sys.exit(1)
    
    print(f"   API key length: {len(api_key)} characters")
    
    # Process
    print("\n" + "=" * 60)
    print("🔄 Processing...")
    print("=" * 60)
    
    try:
        # Step 1: Get encryption key
        server_public_key = get_encryption_key(agent_url)
        
        # Step 2: Encrypt the API key
        print("\n🔐 Encrypting API key...")
        nonce, ephemeral_pub_key, encrypted_key = encrypt_api_key(
            server_public_key, api_key
        )
        print("✅ API key encrypted successfully")
        
        # Step 3: Send to server
        result = set_encrypted_apikey(agent_url, nonce, ephemeral_pub_key, encrypted_key)
        
        print("\n" + "=" * 60)
        print("🎉 SUCCESS!")
        print("=" * 60)
        print(f"   Status: {result.get('status', 'unknown')}")
        print(f"   Message: {result.get('message', 'No message')}")
        print("\nYou can now use the /chat endpoint to interact with OpenAI.")
        
    except requests.exceptions.ConnectionError as e:
        print(f"\n❌ Connection failed: Cannot reach {agent_url}")
        print(f"   Details: {e}")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print(f"\n❌ Request timed out for {agent_url}")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP error: {e}")
        try:
            print(f"   Response: {e.response.json()}")
        except Exception:
            print(f"   Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
