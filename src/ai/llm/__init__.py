"""
Hyperdraft LLM Subsystem

Provides LLM integration for AI strategy generation and decision-making.
Supports local models via Ollama, OpenAI API fallback, and Claude Code
subprocess (no API key — uses OAuth creds at ~/.claude/.credentials.json).
"""

from .base import LLMProvider, LLMResponse
from .config import LLMConfig, ProviderType
from .cache import LLMCache
from .ollama_provider import OllamaProvider
from .api_provider import OpenAIProvider, ClaudeCodeProvider

__all__ = [
    'LLMProvider',
    'LLMResponse',
    'LLMConfig',
    'ProviderType',
    'LLMCache',
    'OllamaProvider',
    'OpenAIProvider',
    'ClaudeCodeProvider',
]
