#!/usr/bin/env python3
"""
Coin Price Bot - A TEE-based service for fetching and analyzing cryptocurrency prices.

This service runs inside an AWS Nitro Enclave using the enclaver tool.
It fetches price information from multiple sources and provides AI-powered analysis.
"""

import json
import os
import time
import logging
from typing import Dict, Any, List, Optional

from flask import Flask, jsonify, request

from enclave import Enclave
from utils import url_prompt, extract_urls, fetch_html, summary_prompt, final_summary_prompt
from tee_client import TEEClient

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

# Default Chat-bot TEE endpoint for AI queries
DEFAULT_CHAT_BOT_ENDPOINT = "https://81.app.zfdang.com"

# Custom chat-bot endpoint (can be set via API)
_custom_chat_bot_endpoint: Optional[str] = None

# Initialize enclave helper
enclave = Enclave(ODYN_API)

# Initialize TEE client for chat-bot
tee_client = None


def get_chat_bot_endpoint() -> str:
    """Get the current chat-bot endpoint (custom or default)."""
    return _custom_chat_bot_endpoint if _custom_chat_bot_endpoint else DEFAULT_CHAT_BOT_ENDPOINT


def get_tee_client():
    """Lazy initialization of TEE client. Reinitializes if endpoint changed."""
    global tee_client
    current_endpoint = get_chat_bot_endpoint()
    
    if tee_client is None or tee_client.endpoint != current_endpoint:
        logger.info(f"Initializing TEE client with endpoint: {current_endpoint}")
        tee_client = TEEClient(current_endpoint)
    
    return tee_client


@app.route('/')
def index():
    """Health check endpoint with service information."""
    try:
        address = enclave.eth_address()
        current_endpoint = get_chat_bot_endpoint()
        return jsonify({
            "status": "ok",
            "service": "Coin Price Bot",
            "version": "1.0.0",
            "enclave_address": address,
            "chat_bot_endpoint": current_endpoint,
            "chat_bot_endpoint_is_custom": _custom_chat_bot_endpoint is not None,
            "endpoints": {
                "/": "Health check and service info",
                "/ping": "Simple ping/pong",
                "/attestation": "Get attestation document",
                "/talk": "POST - Query coin prices (requires JSON body)",
                "/set_chat_bot_endpoint": "POST - Set custom chat-bot endpoint",
                "/get_chat_bot_endpoint": "GET - Get current chat-bot endpoint"
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
        # Include the encryption public key in the response for easy client access
        public_key_der = enclave.get_encryption_public_key_der()
        return jsonify({
            "attestation_doc": att_doc,
            "public_key": public_key_der.hex()
        })
    except Exception as e:
        logger.error(f"Attestation error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/set_chat_bot_endpoint', methods=['POST'])
def set_chat_bot_endpoint():
    """
    Set a custom chat-bot endpoint URL.
    
    JSON body:
    {
        "endpoint": "https://example.com"
    }
    
    To reset to default, set endpoint to null or empty string.
    """
    global _custom_chat_bot_endpoint, tee_client
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        endpoint_raw = data.get("endpoint")
        endpoint = (endpoint_raw.strip() if isinstance(endpoint_raw, str) else "") or ""
        
        if endpoint:
            # Validate URL format
            if not endpoint.startswith(("http://", "https://")):
                return jsonify({"error": "Invalid endpoint URL. Must start with http:// or https://"}), 400
            
            _custom_chat_bot_endpoint = endpoint
            # Reset tee_client so it reinitializes with new endpoint
            tee_client = None
            logger.info(f"Chat-bot endpoint set to: {endpoint}")
            
            return jsonify({
                "status": "ok",
                "message": f"Chat-bot endpoint updated to: {endpoint}",
                "endpoint": endpoint,
                "is_custom": True
            })
        else:
            # Reset to default
            _custom_chat_bot_endpoint = None
            tee_client = None
            logger.info(f"Chat-bot endpoint reset to default: {DEFAULT_CHAT_BOT_ENDPOINT}")
            
            return jsonify({
                "status": "ok",
                "message": f"Chat-bot endpoint reset to default: {DEFAULT_CHAT_BOT_ENDPOINT}",
                "endpoint": DEFAULT_CHAT_BOT_ENDPOINT,
                "is_custom": False
            })
            
    except Exception as e:
        logger.error(f"Set chat-bot endpoint error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/get_chat_bot_endpoint')
def get_chat_bot_endpoint_route():
    """Get the current chat-bot endpoint configuration."""
    current_endpoint = get_chat_bot_endpoint()
    return jsonify({
        "endpoint": current_endpoint,
        "default_endpoint": DEFAULT_CHAT_BOT_ENDPOINT,
        "is_custom": _custom_chat_bot_endpoint is not None
    })


@app.route('/talk', methods=['POST'])
def talk():
    """
    Main endpoint for coin price queries.
    
    Accepts encrypted requests in the format:
    {
        "nonce": "hex-encoded-32-bytes",
        "public_key": "hex-encoded-DER-public-key",
        "data": "hex-encoded-encrypted-json"
    }
    
    The encrypted data should contain:
    {
        "api_key": "your-openai-api-key",
        "message": "What is the current price of Bitcoin?",
        "platform": "openai",
        "ai_model": "gpt-4"
    }
    
    Returns encrypted response with signature.
    """
    try:
        request_data = request.get_json()
        
        if not request_data:
            return jsonify({"error": "Request body is required"}), 400
        
        # Check if this is an encrypted request
        if "nonce" in request_data and "public_key" in request_data and "data" in request_data:
            # Encrypted request format
            nonce_hex = request_data.get("nonce", "")
            client_public_key_hex = request_data.get("public_key", "")
            encrypted_data_hex = request_data.get("data", "")
            
            if not nonce_hex or not client_public_key_hex or not encrypted_data_hex:
                return jsonify({"error": "nonce, public_key, and data are required for encrypted requests"}), 400
            
            # Decrypt the request
            logger.info("Decrypting incoming request...")
            try:
                decrypted_str = enclave.decrypt_data(
                    nonce_hex, client_public_key_hex, encrypted_data_hex
                )
                data = json.loads(decrypted_str)
            except Exception as e:
                logger.error(f"Decryption failed: {e}")
                return jsonify({"error": f"Decryption failed: {str(e)}"}), 400
            
            client_public_key_der = bytes.fromhex(client_public_key_hex)
            is_encrypted = True
        else:
            # Legacy plaintext format
            data = request_data
            is_encrypted = False
        
        # Extract fields from decrypted data
        api_key = data.get("api_key", "")
        message = data.get("message", "")
        platform = data.get("platform", "openai")
        ai_model = data.get("ai_model", "gpt-4")
        
        # Validate required fields
        if not api_key:
            return jsonify({"error": "api_key is required"}), 400
        if not message:
            return jsonify({"error": "message is required"}), 400
        
        client = get_tee_client()
        original_message = message
        req_resp_pairs = []
        
        # Step 1: Ask AI to find relevant URLs
        logger.info(f"Step 1: Getting URLs for query: {message[:50]}...")
        url_list_prompt = url_prompt(message)
        
        url_response = client.talk(api_key, url_list_prompt, platform, ai_model)
        if "error" in url_response:
            return jsonify({"error": f"Failed to get URLs: {url_response['error']}"}), 500
        
        req_resp_pairs.append({
            "description": "urls to resolve query",
            "attestation_endpoint": f"{CHAT_BOT_ENDPOINT}/attestation",
            **url_response
        })
        
        # Extract URLs from response
        url_text = url_response.get("data", {}).get("response", "")
        urls = extract_urls(url_text)
        logger.info(f"Extracted URLs: {urls}")
        
        # Step 2: Fetch HTML content for each URL (max 3)
        url_html_dict = {}
        for url in urls[:3]:
            logger.info(f"Fetching HTML for: {url}")
            html = fetch_html(url)
            url_html_dict[url] = html
        
        # Step 3: Summarize each URL's content
        url_summary_dict = {}
        for url, html in url_html_dict.items():
            logger.info(f"Summarizing content for: {url}")
            sp = summary_prompt(original_message, url, html)
            
            summary_response = client.talk(api_key, sp, platform, ai_model)
            if "error" not in summary_response:
                url_summary_dict[url] = summary_response.get("data", {}).get("response", "")
                req_resp_pairs.append({
                    "description": "summaries for the url content",
                    "attestation_endpoint": f"{CHAT_BOT_ENDPOINT}/attestation",
                    **summary_response
                })
            else:
                logger.warning(f"Failed to summarize {url}: {summary_response.get('error')}")
        
        # Step 4: Create final summary
        logger.info("Creating final summary...")
        formatted_summaries = ""
        for i, (url, summary) in enumerate(url_summary_dict.items(), 1):
            formatted_summaries += f"url{i}:\n{url}\nSummary: {summary}\n\n"
        
        final_prompt = final_summary_prompt(original_message, formatted_summaries)
        final_response = client.talk(api_key, final_prompt, platform, ai_model)
        
        if "error" in final_response:
            return jsonify({"error": f"Failed to create final summary: {final_response['error']}"}), 500
        
        req_resp_pairs.append({
            "description": "final summary combining all url content summaries",
            "attestation_endpoint": f"{CHAT_BOT_ENDPOINT}/attestation",
            **final_response
        })
        
        if is_encrypted:
            # Encrypt the response
            logger.info("Encrypting response...")
            response_json = json.dumps(req_resp_pairs, sort_keys=True, separators=(',', ':'))
            encrypted_response, server_public_key_hex, response_nonce_hex = enclave.encrypt_data(
                response_json, client_public_key_der
            )
            
            encrypted_envelope = {
                "nonce": response_nonce_hex,
                "public_key": server_public_key_hex,
                "encrypted_data": encrypted_response
            }
            
            signature = enclave.sign_message(encrypted_envelope)
            
            return jsonify({
                "sig": signature,
                "data": encrypted_envelope
            })
        else:
            # Legacy plaintext response
            signature = enclave.sign_message(req_resp_pairs)
            return jsonify({
                "sig": signature,
                "data": req_resp_pairs
            })
        
    except Exception as e:
        logger.error(f"Talk error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/query')
def test_query():
    """Test endpoint to verify external network access."""
    try:
        import requests
        data = requests.get("https://api.binance.com/api/v3/time", timeout=10).json()
        signature = enclave.sign_message(data)
        return jsonify({
            "sig": signature,
            "data": data
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    logger.info("Starting Coin Price Bot service...")
    logger.info(f"ODYN API endpoint: {ODYN_API}")
    logger.info(f"Chat-bot TEE endpoint: {get_chat_bot_endpoint()}")
    logger.info("Endpoints:")
    logger.info("  GET  /             - Health check")
    logger.info("  GET  /ping         - Ping/pong")
    logger.info("  GET  /attestation  - Get attestation document")
    logger.info("  POST /talk         - Query coin prices")
    
    app.run(host='0.0.0.0', port=8000)
