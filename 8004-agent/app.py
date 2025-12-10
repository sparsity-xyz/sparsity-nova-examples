#!/usr/bin/env python3
"""
8004-Agent - A TEE-based agent service running on AWS Nitro Enclave.

This service runs inside an AWS Nitro Enclave using the enclaver tool.
It provides a simple agent with OpenAI chat integration.
"""

import json
import os
import time
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from flask import Flask, jsonify, request
import httpx

from enclave import Enclave

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Default mock odyn API endpoint
DEFAULT_MOCK_ODYN_API = "http://3.101.68.206:18000"

# Enclaver odyn API endpoint (internal)
ODYN_API = "http://localhost:18000" if os.getenv("IN_DOCKER", "False").lower() == "true" else DEFAULT_MOCK_ODYN_API

# Initialize enclave helper
enclave = Enclave(ODYN_API)

# Agent card path
AGENT_CARD_PATH = Path(os.getenv("AGENT_CARD_PATH", "/app/agent.json"))

# In-memory storage for OpenAI API key
_openai_api_key: Optional[str] = None

# Agent card cache
_agent_card_cache: Optional[Dict] = None
_agent_card_mtime: Optional[float] = None


def load_agent_card(force: bool = False) -> Dict:
    """Load agent card from JSON file if present; otherwise return empty."""
    global _agent_card_cache, _agent_card_mtime
    
    try:
        if AGENT_CARD_PATH.exists():
            mtime = AGENT_CARD_PATH.stat().st_mtime
            if force or _agent_card_cache is None or mtime != _agent_card_mtime:
                with AGENT_CARD_PATH.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("timestamp", int(time.time()))
                    _agent_card_cache = data
                    _agent_card_mtime = mtime
                else:
                    logger.warning("agent.json is not a JSON object; returning empty card")
                    _agent_card_cache = {}
            return _agent_card_cache
        else:
            return {}
    except Exception as e:
        logger.error(f"Failed to load agent card from {AGENT_CARD_PATH}: {e}")
        return {}


@app.route('/')
def index():
    """Health check endpoint with service information."""
    try:
        address = enclave.eth_address()
        return jsonify({
            "status": "ok",
            "service": "8004-Agent",
            "version": "1.0.0",
            "enclave_address": address,
            "api_key_set": _openai_api_key is not None,
            "endpoints": {
                "/": "Health check and service info",
                "/ping": "Simple ping/pong",
                "/attestation": "Get attestation document",
                "/agent.json": "Get agent card",
                "/get_encryption_key": "GET - Get encryption public key and instructions",
                "/set_encrypted_apikey": "POST - Set OpenAI API key (encrypted)",
                "/hello_world": "Simple hello world",
                "/add_two": "POST - Add two numbers",
                "/chat": "POST - Chat with OpenAI"
            }
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/ping')
def ping():
    """Simple ping endpoint."""
    return jsonify({"pong": int(time.time())})


@app.route('/attestation')
def attestation():
    """Get attestation document from the enclave."""
    try:
        att_doc = enclave.get_attestation()
        public_key_der = enclave.get_encryption_public_key_der()
        return jsonify({
            "attestation_doc": att_doc,
            "public_key": public_key_der.hex()
        })
    except Exception as e:
        logger.error(f"Attestation error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/agent.json')
def agent_card():
    """Return JSON metadata card."""
    return jsonify(load_agent_card())


@app.route('/hello_world')
def hello_world():
    """Simple hello world endpoint."""
    return jsonify({"message": "Hello World", "timestamp": int(time.time())})


@app.route('/add_two', methods=['POST'])
def add_two():
    """Add two numbers."""
    try:
        body = request.get_json()
        if not body:
            return jsonify({"error": "Request body is required"}), 400
        
        a = body.get("a")
        b = body.get("b")
        
        if a is None or b is None:
            return jsonify({"error": "Both 'a' and 'b' are required"}), 400
        
        result = int(a) + int(b)
        return jsonify({"result": result, "a": a, "b": b})
    except ValueError as e:
        return jsonify({"error": f"Invalid number format: {e}"}), 400
    except Exception as e:
        logger.error(f"add_two error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/get_encryption_key')
def get_encryption_key():
    """
    Get the encryption public key and instructions for encrypting the API key.
    
    Returns the P-384 public key in DER format (hex) and encryption instructions.
    """
    try:
        public_key_der = enclave.get_encryption_public_key_der()
        
        return jsonify({
            "public_key": public_key_der.hex(),
            "algorithm": "P-384 ECDH + AES-256-GCM",
            "instructions": {
                "step1": "Generate an ephemeral P-384 keypair",
                "step2": "Perform ECDH key exchange with this public_key to get shared secret",
                "step3": "Derive AES key using HKDF-SHA256(shared_secret, salt=None, info='encryption data', length=32)",
                "step4": "Generate a random 32-byte nonce",
                "step5": "Encrypt your API key using AES-256-GCM with the derived key and nonce",
                "step6": "POST to /set_encrypted_apikey with: {nonce: hex, public_key: your_ephemeral_public_key_der_hex, encrypted_key: ciphertext_hex}"
            },
            "example": "See README.md for complete Python example code"
        })
    except Exception as e:
        logger.error(f"get_encryption_key error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/set_encrypted_apikey', methods=['POST'])
def set_encrypted_apikey():
    """
    Set the OpenAI API key for chat endpoint.
    
    The API key must be encrypted. Get the encryption key from /get_encryption_key first.
    
    Request body:
    {
        "nonce": "32-byte-nonce-hex",
        "public_key": "your-ephemeral-public-key-der-hex",
        "encrypted_key": "aes-gcm-ciphertext-hex"
    }
    """
    global _openai_api_key
    
    try:
        body = request.get_json()
        if not body:
            return jsonify({"error": "Request body is required"}), 400
        
        nonce = body.get("nonce")
        public_key = body.get("public_key")
        encrypted_key = body.get("encrypted_key")
        
        if not nonce or not public_key or not encrypted_key:
            return jsonify({
                "error": "'nonce', 'public_key', and 'encrypted_key' are required. Get encryption key from /get_encryption_key first."
            }), 400
        
        # Decrypt the API key
        try:
            api_key = enclave.decrypt_data(nonce, public_key, encrypted_key)
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return jsonify({"error": f"Decryption failed: {str(e)}"}), 400
        
        _openai_api_key = api_key
        logger.info("OpenAI API key has been set (encrypted submission)")
        
        return jsonify({
            "status": "ok",
            "message": "API key has been set successfully"
        })
    except Exception as e:
        logger.error(f"set_encrypted_apikey error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/chat', methods=['POST'])
def chat():
    """
    Chat with OpenAI.
    
    Request body:
    {
        "prompt": "Your message here"
    }
    
    Note: API key must be set via /set_encrypted_apikey first.
    """
    global _openai_api_key
    
    try:
        # Check if API key is set
        if not _openai_api_key:
            return jsonify({
                "error": "OpenAI API key not set",
                "guidance": {
                    "step1": "GET /get_encryption_key to get the server's public key",
                    "step2": "Encrypt your OpenAI API key using the provided instructions",
                    "step3": "POST /set_encrypted_apikey with the encrypted key",
                    "example": "See README.md for complete Python example code"
                }
            }), 400
        
        body = request.get_json()
        if not body:
            return jsonify({"error": "Request body is required"}), 400
        
        prompt = body.get("prompt")
        if not prompt:
            return jsonify({"error": "'prompt' is required"}), 400
        
        logger.info(f"Chat request: {prompt[:50]}...")
        
        # Call OpenAI API
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {_openai_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}]
                }
            )
        
        result = response.json()
        logger.info(f"OpenAI response received")
        
        if "error" in result:
            return jsonify({"error": result["error"]}), 500
        
        return jsonify({
            "response": result["choices"][0]["message"]["content"],
            "timestamp": int(time.time())
        })
        
    except httpx.TimeoutException:
        return jsonify({"error": "OpenAI API request timed out"}), 504
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    logger.info("Starting 8004-Agent service...")
    logger.info(f"ODYN API endpoint: {ODYN_API}")
    logger.info("Endpoints:")
    logger.info("  GET  /                    - Health check")
    logger.info("  GET  /ping                - Ping/pong")
    logger.info("  GET  /attestation         - Get attestation document")
    logger.info("  GET  /agent.json          - Agent card")
    logger.info("  GET  /hello_world         - Hello world")
    logger.info("  POST /add_two             - Add two numbers")
    logger.info("  GET  /get_encryption_key  - Get encryption public key")
    logger.info("  POST /set_encrypted_apikey         - Set OpenAI API key (encrypted)")
    logger.info("  POST /chat                - Chat with OpenAI")
    
    app.run(host='0.0.0.0', port=8000)
