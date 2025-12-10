#!/usr/bin/env python3
"""
8004-Agent - FastAPI version running inside AWS Nitro Enclave.

This service uses FastAPI to expose the same endpoints with automatic
OpenAPI exposure at /openapi.json and Swagger UI at /docs.
"""

import json
import os
import time
import logging
from typing import Dict, Optional
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import JSONResponse

from enclave import Enclave

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="8004-Agent",
    version="1.0.0",
    description="TEE-based agent service running inside AWS Nitro Enclave"
)

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


class AddTwoRequest(BaseModel):
    a: int
    b: int


class SetEncryptedApiKeyRequest(BaseModel):
    nonce: str
    public_key: str
    encrypted_key: str


class ChatRequest(BaseModel):
    prompt: str


def signed_response(data: str) -> Dict[str, str]:
    """Return response with signature and data fields."""
    try:
        sig = enclave.sign_data(data)
        return {"sig": sig, "data": data}
    except Exception as e:
        logger.error(f"Signing failed: {e}")
        raise HTTPException(status_code=500, detail="Signing failed")


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




@app.get("/")
async def index():
    """Health check endpoint with service information."""
    try:
        address = enclave.eth_address()
        return {
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
                "/openapi.json": "OpenAPI schema",
                "/docs": "Swagger UI",
                "/get_encryption_key": "GET - Get encryption public key and instructions",
                "/set_encrypted_apikey": "POST - Set OpenAI API key (encrypted)",
                "/hello_world": "Simple hello world",
                "/add_two": "POST - Add two numbers",
                "/chat": "POST - Chat with OpenAI"
            }
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ping")
async def ping():
    """Simple ping endpoint."""
    return {"pong": int(time.time())}


@app.get("/attestation")
async def attestation():
    """Get attestation document from the enclave."""
    try:
        att_doc = enclave.get_attestation()
        public_key_der = enclave.get_encryption_public_key_der()
        return {
            "attestation_doc": att_doc,
            "public_key": public_key_der.hex()
        }
    except Exception as e:
        logger.error(f"Attestation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agent.json")
async def agent_card():
    """Return JSON metadata card."""
    return load_agent_card()


@app.get("/hello_world")
async def hello_world():
    """Simple hello world endpoint."""
    return signed_response("Hello World")


@app.post("/add_two")
async def add_two(body: AddTwoRequest):
    """Add two numbers."""
    try:
        result = int(body.a) + int(body.b)
        return signed_response(str(result))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid number format: {e}")
    except Exception as e:
        logger.error(f"add_two error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_encryption_key")
async def get_encryption_key():
    """
    Get the encryption public key and instructions for encrypting the API key.
    Returns the P-384 public key in DER format (hex) and encryption instructions.
    """
    try:
        public_key_der = enclave.get_encryption_public_key_der()

        return {
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
        }
    except Exception as e:
        logger.error(f"get_encryption_key error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/set_encrypted_apikey")
async def set_encrypted_apikey(body: SetEncryptedApiKeyRequest):
    """Set the OpenAI API key for chat endpoint."""
    global _openai_api_key

    try:
        # Decrypt the API key
        try:
            api_key = enclave.decrypt_data(body.nonce, body.public_key, body.encrypted_key)
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise HTTPException(status_code=400, detail=f"Decryption failed: {str(e)}")

        _openai_api_key = api_key
        logger.info("OpenAI API key has been set (encrypted submission)")

        return {"status": "ok", "message": "API key has been set successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"set_encrypted_apikey error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat(body: ChatRequest):
    """Chat with OpenAI."""
    global _openai_api_key

    try:
        if not _openai_api_key:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "OpenAI API key not set",
                    "guidance": {
                        "step1": "GET /get_encryption_key to get the server's public key",
                        "step2": "Encrypt your OpenAI API key using the provided instructions",
                        "step3": "POST /set_encrypted_apikey with the encrypted key",
                        "example": "See README.md for complete Python example code"
                    }
                }
            )

        prompt = body.prompt
        if not prompt:
            raise HTTPException(status_code=400, detail="'prompt' is required")

        logger.info(f"Chat request: {prompt[:50]}...")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
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
        logger.info("OpenAI response received")

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        content = result["choices"][0]["message"]["content"]
        return signed_response(content)

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="OpenAI API request timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/openapi.json")
async def custom_openapi():
    """Expose the generated OpenAPI schema explicitly."""
    return JSONResponse(content=app.openapi())


if __name__ == "__main__":
    logger.info("Starting 8004-Agent service (FastAPI)...")
    logger.info(f"ODYN API endpoint: {ODYN_API}")
    logger.info("Endpoints:")
    logger.info("  GET  /                    - Health check")
    logger.info("  GET  /ping                - Ping/pong")
    logger.info("  GET  /attestation         - Get attestation document")
    logger.info("  GET  /agent.json          - Agent card")
    logger.info("  GET  /openapi.json        - OpenAPI schema")
    logger.info("  GET  /docs                - Swagger UI")
    logger.info("  GET  /hello_world         - Hello world")
    logger.info("  POST /add_two             - Add two numbers")
    logger.info("  GET  /get_encryption_key  - Get encryption public key")
    logger.info("  POST /set_encrypted_apikey         - Set OpenAI API key (encrypted)")
    logger.info("  POST /chat                - Chat with OpenAI")

    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000)
