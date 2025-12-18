"""
Anthropic (Claude) platform integration.
"""

import time
from typing import Tuple
from anthropic import Anthropic as AnClient

from .platform import Platform


class Anthropic(Platform):
    """Anthropic/Claude platform integration."""
    
    name = "anthropic"
    
    def __init__(self, api_key: str):
        """
        Initialize Anthropic client.
        
        Args:
            api_key: Anthropic API key.
        """
        super().__init__(api_key)
        self.client = AnClient(api_key=api_key)
    
    def call(self, model: str, message: str) -> Tuple[str, int]:
        """
        Call Anthropic messages API.
        
        Args:
            model: Model name (e.g., "claude-3-7-sonnet-20250219").
            message: User message.
            
        Returns:
            Tuple of (response content, timestamp).
        """
        response = self.client.messages.create(
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": message,
                }
            ],
            model=model,
        )
        return response.content[0].text, int(time.time())
