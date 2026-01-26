"""
Ollama LLM Provider

Local LLM integration using Ollama.
Models are managed by Ollama and cached in ~/.ollama/models/.
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


class OllamaProvider(LLMProvider):
    """
    LLM provider using local Ollama instance.

    Setup:
        1. Install Ollama: curl -fsSL https://ollama.com/install.sh | sh
        2. Pull a model: ollama pull qwen2.5:3b
        3. Start Ollama service: ollama serve (or it runs automatically)

    Models are stored in ~/.ollama/models/ and persist across runs.
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "qwen2.5:3b",
        timeout: float = 30.0
    ):
        """
        Initialize Ollama provider.

        Args:
            host: Ollama API host URL
            model: Model name (e.g., "qwen2.5:3b", "deepseek-r1:7b")
            timeout: Request timeout in seconds
        """
        self.host = host.rstrip('/')
        self.model = model
        self.timeout = timeout
        self._available: Optional[bool] = None

    @property
    def is_available(self) -> bool:
        """Check if Ollama is running and the model is available."""
        if not AIOHTTP_AVAILABLE:
            self._available = False
            return False

        if self._available is not None:
            return self._available

        try:
            import requests
            # Check if Ollama is running
            r = requests.get(f"{self.host}/api/tags", timeout=2)
            if r.status_code != 200:
                self._available = False
                return False

            # Check if our model is available
            models = r.json().get('models', [])
            model_names = [m.get('name', '') for m in models]

            # Check for exact match or partial match (e.g., "qwen2.5:3b" in "qwen2.5:3b")
            base_model = self.model.split(':')[0]
            self._available = any(
                self.model in name or base_model in name
                for name in model_names
            )

            if not self._available:
                print(f"Model '{self.model}' not found. Available: {model_names}")
                print(f"Run: ollama pull {self.model}")

            return self._available

        except Exception as e:
            self._available = False
            return False

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
        """
        Generate a completion using Ollama.

        Args:
            prompt: The user prompt
            system: Optional system prompt
            temperature: Sampling temperature

        Returns:
            LLMResponse with generated content
        """
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp not installed. Run: pip install aiohttp")

        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature
                }
            }

            if system:
                payload["system"] = system

            async with session.post(
                f"{self.host}/api/generate",
                json=payload
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"Ollama error {resp.status}: {error_text}")

                data = await resp.json()

                return LLMResponse(
                    content=data.get("response", ""),
                    model=self.model,
                    tokens_used=data.get("eval_count", 0),
                    raw_response=data
                )

    async def complete_json(
        self,
        prompt: str,
        schema: dict,
        system: Optional[str] = None,
        temperature: float = 0.1
    ) -> dict:
        """
        Generate a JSON-structured completion.

        Adds JSON formatting instructions and parses the response.

        Args:
            prompt: The user prompt
            schema: Expected JSON schema (used for documentation)
            system: Optional system prompt
            temperature: Sampling temperature

        Returns:
            Parsed JSON dict
        """
        # Add JSON instruction to prompt
        schema_str = json.dumps(schema, indent=2)
        json_prompt = f"""{prompt}

Respond with ONLY valid JSON matching this schema:
{schema_str}

JSON response:"""

        # Add system instruction for JSON
        json_system = system or ""
        json_system += "\nYou MUST respond with valid JSON only. No explanations, no markdown."

        response = await self.complete(
            prompt=json_prompt,
            system=json_system,
            temperature=temperature
        )

        # Parse JSON from response
        return self._parse_json_response(response.content, schema)

    def _parse_json_response(self, content: str, schema: dict) -> dict:
        """
        Parse JSON from LLM response, handling common formatting issues.

        Args:
            content: Raw LLM response
            schema: Expected schema for defaults

        Returns:
            Parsed JSON dict
        """
        # Clean up common issues
        content = content.strip()

        # Remove markdown code blocks
        if content.startswith("```"):
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)

        # Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in response
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Return defaults from schema
        return self._defaults_from_schema(schema)

    def _defaults_from_schema(self, schema: dict) -> dict:
        """Generate default values from a JSON schema."""
        result = {}

        for key, value in schema.items():
            if isinstance(value, str):
                # Type hint string like "str", "float", "list[str]"
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

    def check_model_status(self) -> dict:
        """
        Get detailed status of the model.

        Returns dict with:
            - available: bool
            - model: str
            - size: str (if available)
            - error: str (if any)
        """
        try:
            import requests
            r = requests.get(f"{self.host}/api/tags", timeout=2)

            if r.status_code != 200:
                return {
                    "available": False,
                    "model": self.model,
                    "error": f"Ollama not responding (status {r.status_code})"
                }

            models = r.json().get('models', [])

            for m in models:
                if self.model in m.get('name', ''):
                    return {
                        "available": True,
                        "model": m.get('name'),
                        "size": m.get('size', 'unknown'),
                        "modified_at": m.get('modified_at')
                    }

            return {
                "available": False,
                "model": self.model,
                "error": f"Model not found. Run: ollama pull {self.model}",
                "available_models": [m.get('name') for m in models]
            }

        except Exception as e:
            return {
                "available": False,
                "model": self.model,
                "error": f"Cannot connect to Ollama: {str(e)}"
            }
