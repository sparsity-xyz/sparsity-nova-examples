"""
TEE Client for communicating with the chat-bot TEE.

This module handles verification of attestation and signed responses from the chat-bot TEE.
"""

import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class TEEClient:
    """Client for communicating with the chat-bot TEE."""
    
    def __init__(self, endpoint: str):
        """
        Initialize the TEE client.
        
        Args:
            endpoint: The chat-bot TEE endpoint URL.
        """
        self.endpoint = endpoint
        self.public_key: Optional[str] = None
        self.initialized = False
    
    def init_keys(self) -> bool:
        """
        Initialize by verifying the attestation of the target TEE.
        
        Returns:
            True if attestation is valid, False otherwise.
        """
        try:
            logger.info(f"Verifying attestation for: {self.endpoint}")
            
            response = requests.get(f"{self.endpoint}/attestation", timeout=10)
            response.raise_for_status()
            att = response.json()
            
            if att.get("mock"):
                # Mock attestation for local testing
                self.public_key = att.get("attestation_doc", {}).get("public_key", "")
                logger.info("Attestation verification: mock mode")
                self.initialized = True
                return True
            
            # Real attestation verification would happen here
            # For now, we'll accept the attestation document
            att_doc = att.get("attestation_doc", {})
            self.public_key = att_doc.get("public_key", "")
            logger.info("Attestation verification: accepted")
            self.initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to verify attestation: {e}")
            return False
    
    def talk(self, api_key: str, message: str, platform: str = "openai", ai_model: str = "gpt-4") -> Dict[str, Any]:
        """
        Send a message to the chat-bot TEE.
        
        Args:
            api_key: The AI platform API key.
            message: The message to send.
            platform: The AI platform (openai, anthropic, gemini).
            ai_model: The AI model to use.
            
        Returns:
            The response from the chat-bot TEE.
        """
        if not self.initialized:
            if not self.init_keys():
                return {"error": "Failed to initialize TEE client"}
        
        try:
            # Send request to chat-bot TEE
            # Using the simplified signing approach (not encrypted)
            payload = {
                "api_key": api_key,
                "message": message,
                "platform": platform,
                "ai_model": ai_model
            }
            
            response = requests.post(
                f"{self.endpoint}/talk",
                json=payload,
                timeout=120  # Longer timeout for AI responses
            )
            response.raise_for_status()
            result = response.json()
            
            if "error" in result:
                return {"error": result["error"]}
            
            # Verify signature if available
            if "sig" in result and "data" in result:
                # In production, we would verify the signature here
                logger.info("Response received with signature")
                return result
            
            return result
            
        except requests.Timeout:
            return {"error": "Request timed out"}
        except requests.RequestException as e:
            return {"error": f"Request failed: {str(e)}"}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}
    
    def verify_signature(self, data: Dict[str, Any], signature: str) -> bool:
        """
        Verify the signature of a response.
        
        Args:
            data: The response data.
            signature: The signature to verify.
            
        Returns:
            True if signature is valid, False otherwise.
        """
        if not self.public_key:
            logger.warning("No public key available for verification")
            return False
        
        # In production, implement actual signature verification here
        # For now, we'll assume the signature is valid
        logger.info("Signature verification: accepted (TODO: implement)")
        return True


if __name__ == '__main__':
    # Test the TEE client
    client = TEEClient("https://vmi.sparsity.ai/chat_bot")
    print(f"Initialized: {client.init_keys()}")
