"""
Google Gemini platform integration.
"""

from typing import Tuple
from google import genai

from .platform import Platform


class Gemini(Platform):
    """Google Gemini platform integration."""
    
    name = "gemini"
    
    def __init__(self, api_key: str):
        """
        Initialize Gemini client.
        
        Args:
            api_key: Google API key.
        """
        super().__init__(api_key)
        self.client = genai.Client(api_key=api_key)
    
    def call(self, model: str, message: str) -> Tuple[str, int]:
        """
        Call Gemini generate content API.
        
        Args:
            model: Model name (e.g., "gemini-2.0-flash-001").
            message: User message.
            
        Returns:
            Tuple of (response content, timestamp).
        """
        response = self.client.models.generate_content(
            model=model,
            contents=message
        )
        return response.candidates[0].content.parts[0].text, int(response.create_time.timestamp())
