"""Unified LLM client for Claude and OpenAI."""

from abc import ABC, abstractmethod
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential


class BaseLLMClient(ABC):
    """Base class for LLM clients."""

    @abstractmethod
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text from prompt."""
        pass


class ClaudeClient(BaseLLMClient):
    """Anthropic Claude API client."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096
    ):
        """
        Initialize Claude client.

        Args:
            api_key: Anthropic API key
            model: Model to use
            max_tokens: Maximum tokens to generate
        """
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=30))
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text using Claude."""
        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = self.client.messages.create(**kwargs)
        return response.content[0].text


class OpenAIClient(BaseLLMClient):
    """OpenAI API client."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4-turbo-preview",
        max_tokens: int = 4096
    ):
        """
        Initialize OpenAI client.

        Args:
            api_key: OpenAI API key
            model: Model to use
            max_tokens: Maximum tokens to generate
        """
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=30))
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text using OpenAI."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content


class LLMClient:
    """Unified LLM client factory."""

    def __init__(
        self,
        provider: str,
        api_key: str,
        model: Optional[str] = None,
        max_tokens: int = 4096
    ):
        """
        Initialize LLM client.

        Args:
            provider: "claude" or "openai"
            api_key: API key for the provider
            model: Model to use (optional, uses default)
            max_tokens: Maximum tokens to generate
        """
        self.provider = provider

        if provider == "claude":
            self._client = ClaudeClient(
                api_key=api_key,
                model=model or "claude-sonnet-4-20250514",
                max_tokens=max_tokens
            )
        elif provider == "openai":
            self._client = OpenAIClient(
                api_key=api_key,
                model=model or "gpt-4-turbo-preview",
                max_tokens=max_tokens
            )
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text from prompt."""
        return self._client.generate(prompt, system)

    @classmethod
    def from_config(
        cls,
        provider: str,
        anthropic_key: Optional[str] = None,
        openai_key: Optional[str] = None,
        claude_config: Optional[dict] = None,
        openai_config: Optional[dict] = None
    ) -> "LLMClient":
        """
        Create LLM client from configuration.

        Args:
            provider: "claude" or "openai"
            anthropic_key: Anthropic API key
            openai_key: OpenAI API key
            claude_config: Claude configuration dict
            openai_config: OpenAI configuration dict

        Returns:
            Configured LLMClient
        """
        if provider == "claude":
            if not anthropic_key:
                raise ValueError("ANTHROPIC_API_KEY required for Claude")
            config = claude_config or {}
            return cls(
                provider="claude",
                api_key=anthropic_key,
                model=config.get("model"),
                max_tokens=config.get("max_tokens", 4096)
            )
        elif provider == "openai":
            if not openai_key:
                raise ValueError("OPENAI_API_KEY required for OpenAI")
            config = openai_config or {}
            return cls(
                provider="openai",
                api_key=openai_key,
                model=config.get("model"),
                max_tokens=config.get("max_tokens", 4096)
            )
        else:
            raise ValueError(f"Unknown provider: {provider}")
