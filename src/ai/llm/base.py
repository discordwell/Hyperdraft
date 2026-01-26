"""
LLM Provider Base Classes

Abstract interface for LLM providers (Ollama, OpenAI, Anthropic).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Any


@dataclass
class LLMResponse:
    """Response from an LLM completion."""
    content: str
    model: str
    tokens_used: int
    cached: bool = False
    raw_response: Optional[Any] = None


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    All providers must implement async completion methods
    for both raw text and JSON-structured output.
    """

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.3
    ) -> LLMResponse:
        """
        Generate a completion for the given prompt.

        Args:
            prompt: The user prompt
            system: Optional system prompt
            temperature: Sampling temperature (0.0-1.0)

        Returns:
            LLMResponse with generated content
        """
        pass

    @abstractmethod
    async def complete_json(
        self,
        prompt: str,
        schema: dict,
        system: Optional[str] = None,
        temperature: float = 0.1
    ) -> dict:
        """
        Generate a JSON-structured completion.

        Args:
            prompt: The user prompt
            schema: JSON schema describing expected output
            system: Optional system prompt
            temperature: Sampling temperature (lower for structured output)

        Returns:
            Parsed JSON dict matching the schema
        """
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is available and ready."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier."""
        pass
