"""
API LLM Providers

Fallback providers for when local Ollama is unavailable:
- OpenAIProvider: HTTP to api.openai.com
- ClaudeCodeProvider: shells out to `claude -p` (uses OAuth creds at
  ~/.claude/.credentials.json, no API key needed)
"""

import asyncio
import json
import re
import shutil
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


class ClaudeCodeProvider(LLMProvider):
    """
    LLM provider that shells out to the `claude` CLI in non-interactive
    (-p) mode. Uses the OAuth credentials in ~/.claude/.credentials.json,
    so no API key is required.

    Trades latency (subprocess spawn per call) for zero-cost-per-token
    via the Claude Code subscription.
    """

    def __init__(
        self,
        model: str = "",
        timeout: float = 120.0,
        claude_bin: str = "claude",
    ):
        """
        Args:
            model: Optional model alias passed to `claude --model` (e.g.
                "haiku", "sonnet", "opus", or a full model ID). Empty
                string lets the CLI pick its default.
            timeout: Subprocess timeout in seconds.
            claude_bin: Path or name of the claude CLI binary.
        """
        self.model = model
        self.timeout = timeout
        self.claude_bin = claude_bin

    @property
    def is_available(self) -> bool:
        return shutil.which(self.claude_bin) is not None

    @property
    def model_name(self) -> str:
        return self.model or "claude-code"

    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.3
    ) -> LLMResponse:
        cmd = [self.claude_bin, "-p", "--output-format", "text"]
        if self.model:
            cmd.extend(["--model", self.model])
        if system:
            cmd.extend(["--append-system-prompt", system])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(prompt.encode("utf-8")),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"claude -p timed out after {self.timeout}s")

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"claude -p exit {proc.returncode}: {err}")

        content = stdout.decode("utf-8", errors="replace").strip()
        return LLMResponse(
            content=content,
            model=self.model_name,
            tokens_used=0,
            raw_response=None,
        )

    async def complete_json(
        self,
        prompt: str,
        schema: dict,
        system: Optional[str] = None,
        temperature: float = 0.1
    ) -> dict:
        schema_str = json.dumps(schema, indent=2)
        json_prompt = f"""{prompt}

Respond with ONLY valid JSON matching this schema:
{schema_str}

JSON:"""
        json_system = (system or "") + "\nRespond with valid JSON only. No explanations."

        response = await self.complete(
            prompt=json_prompt,
            system=json_system,
            temperature=temperature,
        )

        return self._parse_json_response(response.content, schema)

    def _parse_json_response(self, content: str, schema: dict) -> dict:
        content = content.strip()

        if content.startswith("```"):
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return self._defaults_from_schema(schema)

    def _defaults_from_schema(self, schema: dict) -> dict:
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
    3. Claude Code subprocess (if `claude` CLI is on PATH)

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

        if config.openai_key:
            return OpenAIProvider(
                api_key=config.openai_key,
                model=config.openai_model,
                timeout=config.timeout
            )
        cc = ClaudeCodeProvider(
            model=config.claude_code_model,
            timeout=max(config.timeout, 60.0),
        )
        if cc.is_available:
            return cc

        raise RuntimeError(
            "Ollama not available, no OPENAI_API_KEY set, and `claude` CLI "
            f"not found on PATH. Run 'ollama pull {config.ollama_model}', "
            "set OPENAI_API_KEY, or install Claude Code."
        )

    elif config.provider == ProviderType.OPENAI:
        if not config.openai_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        return OpenAIProvider(
            api_key=config.openai_key,
            model=config.openai_model,
            timeout=config.timeout
        )

    elif config.provider == ProviderType.CLAUDE_CODE:
        provider = ClaudeCodeProvider(
            model=config.claude_code_model,
            timeout=max(config.timeout, 60.0),
        )
        if not provider.is_available:
            raise RuntimeError(
                "`claude` CLI not found on PATH. Install Claude Code or "
                "pick a different provider."
            )
        return provider

    raise RuntimeError(f"Unknown provider type: {config.provider}")
