#!/usr/bin/env python3
"""
AI Chatbot - A TEE-based AI chat service running on Sparsity Nova Platform.

This service runs inside an AWS Nitro Enclave using the enclaver tool.
It provides secure AI chat functionality with signed responses.
"""

import json
import os
import time
import logging
from typing import Dict, Any, Optional

from flask import Flask, jsonify, request
from pydantic import BaseModel

from enclave import Enclave
from ai_models.open_ai import OpenAI
from ai_models.anthropic import Anthropic
from ai_models.gemini import Gemini
from ai_models.platform import Platform

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Enclaver odyn API endpoint (internal)
ODYN_API = "http://localhost:18000" if os.getenv("IN_DOCKER", "False").lower() == "true" else os.getenv("MOCK_ODYN_API", "http://54.215.216.173:18000")

# Initialize enclave helper
enclave = Enclave(ODYN_API)

# Platform mapping
PLATFORM_MAPPING: Dict[str, type] = {
    "openai": OpenAI,
    "anthropic": Anthropic,
    "gemini": Gemini,
}


@app.route('/')
def index():
    """Health check endpoint with service information."""
    try:
        address = enclave.eth_address()
        return jsonify({
            "status": "ok",
            "service": "AI Chatbot",
            "version": "1.0.0",
            "enclave_address": address,
            "supported_platforms": list(PLATFORM_MAPPING.keys()),
            "endpoints": {
                "/": "Health check and service info",
                "/ping": "Simple ping/pong",
                "/attestation": "Get attestation document",
                "/talk": "POST - Send chat message (requires JSON body)"
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
        if att_doc.get("mock"):
            return jsonify({
                "attestation_doc": att_doc,
                "mock": True
            })
        return jsonify({
            "attestation_doc": att_doc
        })
    except Exception as e:
        logger.error(f"Attestation error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/talk', methods=['POST'])
def talk():
    """
    Main chat endpoint. Receives a message and returns a signed AI response.
    
    Expected JSON body:
    {
        "api_key": "your-api-key",
        "message": "Hello, AI!",
        "platform": "openai",  // openai, anthropic, or gemini
        "ai_model": "gpt-4"    // model name for the platform
    }
    
    Returns:
    {
        "sig": "hex-signature",
        "data": {
            "platform": "openai",
            "ai_model": "gpt-4",
            "timestamp": 1234567890,
            "message": "Hello, AI!",
            "response": "Hello! How can I help you today?"
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        api_key = data.get("api_key", "")
        message = data.get("message", "")
        platform = data.get("platform", "openai")
        ai_model = data.get("ai_model", "gpt-4")
        
        # Validate required fields
        if not api_key:
            return jsonify({"error": "api_key is required"}), 400
        if not message:
            return jsonify({"error": "message is required"}), 400
        
        # Validate platform
        platform_class = PLATFORM_MAPPING.get(platform)
        if platform_class is None:
            return jsonify({
                "error": f"Invalid platform: {platform}. Supported: {list(PLATFORM_MAPPING.keys())}"
            }), 400
        
        # Create platform client and validate model
        client: Platform = platform_class(api_key)
        if not client.check_support_model(ai_model):
            return jsonify({
                "error": f"Invalid model: {ai_model}. Supported for {platform}: {client.support_models}"
            }), 400
        
        # Call AI model
        logger.info(f"Calling {platform}/{ai_model} with message: {message[:50]}...")
        resp_content, resp_timestamp = client.call(ai_model, message)
        
        # Build response data
        response_data = {
            "platform": platform,
            "ai_model": ai_model,
            "timestamp": resp_timestamp,
            "message": message,
            "response": resp_content
        }
        
        # Sign the response
        signature = enclave.sign_message(response_data)
        
        return jsonify({
            "sig": signature,
            "data": response_data
        })
        
    except Exception as e:
        logger.error(f"Talk error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    logger.info("Starting AI Chatbot service...")
    logger.info(f"ODYN API endpoint: {ODYN_API}")
    logger.info("Endpoints:")
    logger.info("  GET  /             - Health check")
    logger.info("  GET  /ping         - Ping/pong")
    logger.info("  GET  /attestation  - Get attestation document")
    logger.info("  POST /talk         - Send chat message")
    
    app.run(host='0.0.0.0', port=8000)
