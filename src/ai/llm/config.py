"""
LLM Configuration

Settings for LLM providers and model selection.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import os


class ProviderType(str, Enum):
    """Supported LLM provider types."""
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class ModelTier(str, Enum):
    """Model capability tiers."""
    LOW_END = "low_end"      # CPU-only, minimal RAM
    BALANCED = "balanced"    # Default, most machines
    HIGH_END = "high_end"    # GPU available


# Recommended models by tier
RECOMMENDED_MODELS = {
    ModelTier.LOW_END: {
        'ollama': 'qwen2.5:1.5b',
        'description': 'Qwen 2.5 1.5B - CPU-only machines',
        'ram_needed': '2GB'
    },
    ModelTier.BALANCED: {
        'ollama': 'qwen2.5:3b',
        'description': 'Qwen 2.5 3B - Most machines (default)',
        'ram_needed': '4GB'
    },
    ModelTier.HIGH_END: {
        'ollama': 'deepseek-r1:7b',
        'description': 'DeepSeek R1 7B - GPU available',
        'ram_needed': '8GB'
    }
}


@dataclass
class LLMConfig:
    """Configuration for LLM providers."""

    # Provider settings
    provider: ProviderType = ProviderType.OLLAMA

    # Ollama settings
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"

    # OpenAI settings
    openai_model: str = "gpt-4o-mini"

    # Anthropic settings
    anthropic_model: str = "claude-3-haiku-20240307"

    # Generation settings
    temperature: float = 0.3
    timeout: float = 30.0
    max_retries: int = 3

    # Caching
    enable_cache: bool = True
    cache_ttl_seconds: int = 86400  # 24 hours

    # API keys from environment
    @property
    def openai_key(self) -> str:
        """Get OpenAI API key from environment."""
        return os.environ.get("OPENAI_API_KEY", "")

    @property
    def anthropic_key(self) -> str:
        """Get Anthropic API key from environment."""
        return os.environ.get("ANTHROPIC_API_KEY", "")

    @classmethod
    def for_tier(cls, tier: ModelTier) -> 'LLMConfig':
        """Create config optimized for a model tier."""
        model_info = RECOMMENDED_MODELS[tier]
        return cls(
            provider=ProviderType.OLLAMA,
            ollama_model=model_info['ollama']
        )

    @classmethod
    def for_api_fallback(cls) -> 'LLMConfig':
        """Create config for API fallback when local unavailable."""
        # Prefer Anthropic if key available, else OpenAI
        if os.environ.get("ANTHROPIC_API_KEY"):
            return cls(provider=ProviderType.ANTHROPIC)
        elif os.environ.get("OPENAI_API_KEY"):
            return cls(provider=ProviderType.OPENAI)
        else:
            # Default to Ollama even if not available
            return cls(provider=ProviderType.OLLAMA)
