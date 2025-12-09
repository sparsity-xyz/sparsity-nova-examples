"""
Base Platform class for AI model integrations.
"""

import abc
from typing import List, Tuple


# Supported models for each platform
PLATFORM_MODELS = {
    "openai": ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
    "anthropic": ["claude-3-7-sonnet-20250219", "claude-3-opus-20240229", "claude-3-sonnet-20240229"],
    "gemini": ["gemini-2.0-flash-001", "gemini-1.5-pro", "gemini-1.5-flash"]
}


class Platform(abc.ABC):
    """Abstract base class for AI platform integrations."""
    
    name: str
    support_models: List[str]
    
    def __init__(self, api_key: str):
        """
        Initialize the platform with an API key.
        
        Args:
            api_key: The API key for the platform.
        """
        self.api_key = api_key
        self.support_models = PLATFORM_MODELS.get(self.name, [])
    
    def check_support_model(self, model: str) -> bool:
        """
        Check if the model is supported by this platform.
        
        Args:
            model: The model name to check.
            
        Returns:
            True if the model is supported, False otherwise.
        """
        return model in self.support_models
    
    @abc.abstractmethod
    def call(self, model: str, message: str) -> Tuple[str, int]:
        """
        Call the AI model with a message.
        
        Args:
            model: The model name to use.
            message: The user message to send.
            
        Returns:
            A tuple of (response_content, timestamp).
        """
        raise NotImplementedError
