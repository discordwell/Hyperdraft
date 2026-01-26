"""
API LLM Providers

Fallback providers for OpenAI and Anthropic APIs.
Used when local Ollama is unavailable.
"""

import json
import re
from typing import Optional

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    aiohttp = None

from .base import LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    """
    LLM provider using OpenAI API.

    Requires OPENAI_API_KEY environment variable.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        timeout: float = 30.0
    ):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key
            model: Model name (e.g., "gpt-4o-mini", "gpt-4o")
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @property
    def is_available(self) -> bool:
        """Check if API key is set."""
        return bool(self.api_key)

    @property
    def model_name(self) -> str:
        """Return the model identifier."""
        return self.model

    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.3
    ) -> LLMResponse:
        """Generate a completion using OpenAI API."""
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp not installed. Run: pip install aiohttp")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature
                }
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"OpenAI error {resp.status}: {error_text}")

                data = await resp.json()

                return LLMResponse(
                    content=data["choices"][0]["message"]["content"],
                    model=self.model,
                    tokens_used=data.get("usage", {}).get("total_tokens", 0),
                    raw_response=data
                )

    async def complete_json(
        self,
        prompt: str,
        schema: dict,
        system: Optional[str] = None,
        temperature: float = 0.1
    ) -> dict:
        """Generate a JSON-structured completion."""
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp not installed. Run: pip install aiohttp")

        messages = []

        json_system = (system or "") + "\nRespond with valid JSON only."
        messages.append({"role": "system", "content": json_system})

        schema_str = json.dumps(schema, indent=2)
        json_prompt = f"""{prompt}

Respond with JSON matching this schema:
{schema_str}"""
        messages.append({"role": "user", "content": json_prompt})

        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "response_format": {"type": "json_object"}
                }
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"OpenAI error {resp.status}: {error_text}")

                data = await resp.json()
                content = data["choices"][0]["message"]["content"]

                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return self._defaults_from_schema(schema)

    def _defaults_from_schema(self, schema: dict) -> dict:
        """Generate default values from a JSON schema."""
        result = {}
        for key, value in schema.items():
            if isinstance(value, str):
                if value == "str":
                    result[key] = ""
                elif value == "float":
                    result[key] = 0.5
                elif value == "int":
                    result[key] = 0
                elif value == "bool":
                    result[key] = False
                elif value.startswith("list"):
                    result[key] = []
                else:
                    result[key] = ""
            elif isinstance(value, dict):
                result[key] = self._defaults_from_schema(value)
            elif isinstance(value, list):
                result[key] = []
            else:
                result[key] = value
        return result


class AnthropicProvider(LLMProvider):
    """
    LLM provider using Anthropic API.

    Requires ANTHROPIC_API_KEY environment variable.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-haiku-20240307",
        timeout: float = 30.0
    ):
        """
        Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key
            model: Model name (e.g., "claude-3-haiku-20240307")
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @property
    def is_available(self) -> bool:
        """Check if API key is set."""
        return bool(self.api_key)

    @property
    def model_name(self) -> str:
        """Return the model identifier."""
        return self.model

    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.3
    ) -> LLMResponse:
        """Generate a completion using Anthropic API."""
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp not installed. Run: pip install aiohttp")

        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature
        }

        if system:
            payload["system"] = system

        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json=payload
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"Anthropic error {resp.status}: {error_text}")

                data = await resp.json()

                content = ""
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        content += block.get("text", "")

                return LLMResponse(
                    content=content,
                    model=self.model,
                    tokens_used=data.get("usage", {}).get("input_tokens", 0) +
                               data.get("usage", {}).get("output_tokens", 0),
                    raw_response=data
                )

    async def complete_json(
        self,
        prompt: str,
        schema: dict,
        system: Optional[str] = None,
        temperature: float = 0.1
    ) -> dict:
        """Generate a JSON-structured completion."""
        schema_str = json.dumps(schema, indent=2)
        json_prompt = f"""{prompt}

Respond with ONLY valid JSON matching this schema:
{schema_str}

JSON:"""

        json_system = (system or "") + "\nRespond with valid JSON only. No explanations."

        response = await self.complete(
            prompt=json_prompt,
            system=json_system,
            temperature=temperature
        )

        return self._parse_json_response(response.content, schema)

    def _parse_json_response(self, content: str, schema: dict) -> dict:
        """Parse JSON from response."""
        content = content.strip()

        # Remove markdown code blocks
        if content.startswith("```"):
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return self._defaults_from_schema(schema)

    def _defaults_from_schema(self, schema: dict) -> dict:
        """Generate default values from schema."""
        result = {}
        for key, value in schema.items():
            if isinstance(value, str):
                if value == "str":
                    result[key] = ""
                elif value == "float":
                    result[key] = 0.5
                elif value == "int":
                    result[key] = 0
                elif value == "bool":
                    result[key] = False
                elif value.startswith("list"):
                    result[key] = []
                else:
                    result[key] = ""
            elif isinstance(value, dict):
                result[key] = self._defaults_from_schema(value)
            elif isinstance(value, list):
                result[key] = []
            else:
                result[key] = value
        return result


def get_provider(config) -> LLMProvider:
    """
    Get the appropriate LLM provider based on config.

    Falls back through providers if primary is unavailable:
    1. Ollama (if configured and available)
    2. OpenAI (if API key available)
    3. Anthropic (if API key available)

    Args:
        config: LLMConfig instance

    Returns:
        Available LLMProvider

    Raises:
        RuntimeError: If no provider is available
    """
    from .ollama_provider import OllamaProvider
    from .config import ProviderType

    if config.provider == ProviderType.OLLAMA:
        provider = OllamaProvider(
            host=config.ollama_host,
            model=config.ollama_model,
            timeout=config.timeout
        )
        if provider.is_available:
            return provider

        # Fallback to API
        if config.openai_key:
            return OpenAIProvider(
                api_key=config.openai_key,
                model=config.openai_model,
                timeout=config.timeout
            )
        if config.anthropic_key:
            return AnthropicProvider(
                api_key=config.anthropic_key,
                model=config.anthropic_model,
                timeout=config.timeout
            )

        raise RuntimeError(
            "Ollama not available and no API keys configured. "
            f"Run 'ollama pull {config.ollama_model}' or set OPENAI_API_KEY/ANTHROPIC_API_KEY"
        )

    elif config.provider == ProviderType.OPENAI:
        if not config.openai_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        return OpenAIProvider(
            api_key=config.openai_key,
            model=config.openai_model,
            timeout=config.timeout
        )

    elif config.provider == ProviderType.ANTHROPIC:
        if not config.anthropic_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        return AnthropicProvider(
            api_key=config.anthropic_key,
            model=config.anthropic_model,
            timeout=config.timeout
        )

    raise RuntimeError(f"Unknown provider type: {config.provider}")
