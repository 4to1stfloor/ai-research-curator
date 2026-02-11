"""Unified LLM client for Claude, OpenAI, Ollama, and Gemini."""

from abc import ABC, abstractmethod
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential


class BaseLLMClient(ABC):
    """Base class for LLM clients."""

    @abstractmethod
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text from prompt."""
        pass


class GeminiClient(BaseLLMClient):
    """Google Gemini API client."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        max_tokens: int = 8192
    ):
        """
        Initialize Gemini client.

        Args:
            api_key: Google API key
            model: Model to use
            max_tokens: Maximum tokens to generate
        """
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)
        self.max_tokens = max_tokens

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=30))
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text using Gemini."""
        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{prompt}"

        response = self.model.generate_content(
            full_prompt,
            generation_config={
                "max_output_tokens": self.max_tokens,
                "temperature": 0.7,
            }
        )
        return response.text


class OllamaClient(BaseLLMClient):
    """Ollama local LLM client."""

    def __init__(
        self,
        model: str = "llama3.1:8b",
        base_url: str = "http://localhost:11434",
        max_tokens: int = 4096,
        auto_pull: bool = True
    ):
        """
        Initialize Ollama client.

        Args:
            model: Model to use (llama3.1:8b, mistral, etc.)
            base_url: Ollama server URL
            max_tokens: Maximum tokens to generate
            auto_pull: Automatically download model if not available
        """
        import requests
        self.model = model
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.session = requests.Session()

        # Check if Ollama is running and model is available
        self._ensure_model_available(auto_pull)

    def _check_ollama_running(self) -> bool:
        """Check if Ollama server is running."""
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def _get_available_models(self) -> list[str]:
        """Get list of available models."""
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return []

    def _pull_model(self, model: str) -> bool:
        """Pull/download a model from Ollama registry."""
        import sys
        print(f"[Ollama] Downloading model '{model}'... This may take a while.", file=sys.stderr)
        try:
            response = self.session.post(
                f"{self.base_url}/api/pull",
                json={"name": model, "stream": False},
                timeout=1800  # 30 minutes for large models
            )
            if response.status_code == 200:
                print(f"[Ollama] Model '{model}' downloaded successfully.", file=sys.stderr)
                return True
            else:
                print(f"[Ollama] Failed to download model: {response.text}", file=sys.stderr)
                return False
        except Exception as e:
            print(f"[Ollama] Error downloading model: {e}", file=sys.stderr)
            return False

    def _ensure_model_available(self, auto_pull: bool = True):
        """Ensure the model is available, download if needed."""
        import sys

        # Check if Ollama is running
        if not self._check_ollama_running():
            raise RuntimeError(
                f"Ollama server is not running at {self.base_url}. "
                "Please start Ollama with 'ollama serve' or install from https://ollama.com"
            )

        # Get available models
        available_models = self._get_available_models()

        # Check if model is available (exact match or base name match)
        model_base = self.model.split(":")[0]
        model_available = any(
            self.model == m or self.model.startswith(m.split(":")[0])
            for m in available_models
        ) or any(
            model_base == m.split(":")[0]
            for m in available_models
        )

        if model_available:
            print(f"[Ollama] Model '{self.model}' is available.", file=sys.stderr)
            return

        print(f"[Ollama] Model '{self.model}' not found. Available: {available_models}", file=sys.stderr)

        if auto_pull:
            if self._pull_model(self.model):
                return
            else:
                raise RuntimeError(f"Failed to download model '{self.model}'")
        else:
            raise RuntimeError(
                f"Model '{self.model}' is not available. "
                f"Please run 'ollama pull {self.model}' to download it."
            )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=30))
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text using Ollama."""
        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{prompt}"

        response = self.session.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "num_predict": self.max_tokens
                }
            },
            timeout=300  # 5 minutes for long responses
        )
        response.raise_for_status()
        return response.json()["response"]


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
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        base_url: Optional[str] = None
    ):
        """
        Initialize LLM client.

        Args:
            provider: "claude", "openai", or "ollama"
            api_key: API key for the provider (not needed for ollama)
            model: Model to use (optional, uses default)
            max_tokens: Maximum tokens to generate
            base_url: Base URL for Ollama server
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
        elif provider == "ollama":
            self._client = OllamaClient(
                model=model or "llama3.1",
                base_url=base_url or "http://localhost:11434",
                max_tokens=max_tokens
            )
        elif provider == "gemini":
            self._client = GeminiClient(
                api_key=api_key,
                model=model or "gemini-2.5-flash",
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
        google_key: Optional[str] = None,
        claude_config: Optional[dict] = None,
        openai_config: Optional[dict] = None,
        ollama_config: Optional[dict] = None,
        gemini_config: Optional[dict] = None
    ) -> "LLMClient":
        """
        Create LLM client from configuration.

        Args:
            provider: "claude", "openai", "ollama", or "gemini"
            anthropic_key: Anthropic API key
            openai_key: OpenAI API key
            google_key: Google API key
            claude_config: Claude configuration dict
            openai_config: OpenAI configuration dict
            ollama_config: Ollama configuration dict
            gemini_config: Gemini configuration dict

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
        elif provider == "ollama":
            config = ollama_config or {}
            return cls(
                provider="ollama",
                model=config.get("model", "llama3.1"),
                max_tokens=config.get("max_tokens", 4096),
                base_url=config.get("base_url", "http://localhost:11434")
            )
        elif provider == "gemini":
            if not google_key:
                raise ValueError("GOOGLE_API_KEY required for Gemini")
            config = gemini_config or {}
            return cls(
                provider="gemini",
                api_key=google_key,
                model=config.get("model", "gemini-2.5-flash"),
                max_tokens=config.get("max_tokens", 8192)
            )
        else:
            raise ValueError(f"Unknown provider: {provider}")
