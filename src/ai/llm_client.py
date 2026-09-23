"""Unified LLM client for Claude CLI, Claude API, OpenAI, Ollama, and Gemini."""

import json
import os
import re
import subprocess
from abc import ABC, abstractmethod
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential


class BaseLLMClient(ABC):
    """Base class for LLM clients."""

    @abstractmethod
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text from prompt."""
        pass


class ClaudeCLIClient(BaseLLMClient):
    """Claude Code CLI client. Uses Claude subscription, no API key needed."""

    def __init__(self):
        """Initialize Claude CLI client. Verifies 'claude' command and subscription."""
        if not self._check_installed():
            raise RuntimeError(
                "Claude CLI not found. Install Claude Code: "
                "https://docs.anthropic.com/en/docs/claude-code"
            )
        if not self._check_subscription():
            raise RuntimeError(
                "Claude CLI is installed but subscription/login is not active. "
                "Run 'claude' to log in."
            )

    @staticmethod
    def _check_installed() -> bool:
        """Check if Claude CLI is installed."""
        try:
            r = subprocess.run(
                ["claude", "--version"],
                capture_output=True, text=True, timeout=10
            )
            return r.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    @staticmethod
    def _check_subscription() -> bool:
        """Check if Claude CLI subscription/login is active."""
        try:
            r = subprocess.run(
                ["claude", "--print", "-p", "say ok"],
                capture_output=True, text=True, timeout=30
            )
            return r.returncode == 0 and "ok" in r.stdout.lower()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    # Replies that are the assistant talking ABOUT the request instead of doing
    # it. These show up when the CLI retries a flagged prompt on a fallback
    # model: the fallback model sees the retracted turn and comments on it.
    # Such a reply must never reach the report.
    _META_REPLY_PATTERNS = [
        r"안전\s*분류기", r"safety classifier",
        r"이전\s*응답이.{0,20}중단",
        r"다시\s*작성할\s*수\s*없",
        r"가능한\s*대안은",
        r"도와드릴\s*수\s*없",
        r"요청을\s*처리할\s*수\s*없",
        r"I (?:can't|cannot|won't) (?:help|assist|provide)",
    ]

    # The model the CLI fell back to, remembered for the rest of the process so
    # we stop paying for a flagged first attempt on every single call.
    _pinned_model: Optional[str] = None

    @classmethod
    def _is_meta_reply(cls, text: str) -> bool:
        head = (text or "")[:600]
        return any(re.search(p, head, re.IGNORECASE) for p in cls._META_REPLY_PATTERNS)

    # Model to pin to when the default one refuses. Science/medicine papers
    # (oncolytic virus, drug-defense, immunology) routinely trip the default
    # model's classifier; this one handles them. Override with CLAUDE_FALLBACK_MODEL.
    _FALLBACK_MODEL = os.environ.get("CLAUDE_FALLBACK_MODEL", "claude-opus-5")

    @staticmethod
    def _run_cli(full_prompt: str, model: Optional[str] = None) -> tuple:
        """Run the CLI once. Returns (text, swap_to_model_or_None, refused).

        --tools "": we only want plain text back, never tool calls.
        --output-format stream-json: the final `result` field comes back EMPTY
        whenever the CLI swapped models mid-response, so we read the assistant
        messages ourselves and detect the swap.
        """
        cmd = ["claude", "--print", "--tools", "", "--output-format", "stream-json",
               "--verbose"]
        if model:
            cmd += ["--model", model]
        cmd += ["-p", full_prompt]

        # 600s: figure explanations for 7-9 figure papers run to ~12k chars of
        # Korean prose; 300s was cutting it close under load.
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        # A refusal exits non-zero but still writes the full event stream, so
        # parse first and only treat it as a hard error if there is nothing
        # to read.
        if r.returncode != 0 and not r.stdout.strip():
            raise RuntimeError(f"Claude CLI error (rc={r.returncode}): {r.stderr[:500]}")

        events = []
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if not events:
            # Older CLI or unexpected output: treat stdout as text.
            return r.stdout.strip(), None, False

        result_ev = next((e for e in events if e.get("type") == "result"), {})
        refused = result_ev.get("stop_reason") == "refusal" or any(
            e.get("type") == "system" and "refusal" in str(e.get("subtype", ""))
            for e in events
        )
        if result_ev.get("is_error") and not refused:
            raise RuntimeError(
                f"Claude CLI error: subtype={result_ev.get('subtype')} "
                f"api_error_status={result_ev.get('api_error_status')} "
                f"result={str(result_ev.get('result'))[:300]}"
            )

        last_text = ""
        for e in events:
            if e.get("type") != "assistant":
                continue
            content = (e.get("message") or {}).get("content") or []
            text = "".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
            if text:
                last_text = text

        swap_to = None
        for e in events:
            if e.get("type") == "system" and "fallback" in str(e.get("subtype", "")):
                swap_to = e.get("fallback_model") or e.get("new_model") or swap_to

        text = last_text or (result_ev.get("result") or "").strip()
        return text, swap_to, refused

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text using Claude CLI, retrying past mid-response model swaps.

        When the primary model's output trips the CLI's refusal check, the CLI
        retracts that turn and retries on a fallback model *within the same
        session*. The fallback model then sees the retracted turn and often
        replies about it ("the previous response was interrupted...") instead of
        answering, which is how meta-commentary ended up in the 2026-09-16 and
        2026-09-23 reports. The cure is to throw that response away and re-run
        the prompt in a FRESH session pinned to the fallback model, which gets a
        clean answer. We remember the pinned model for later calls in this run.
        """
        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{prompt}"

        cls = type(self)
        last_reason = "unknown"
        for attempt in range(3):
            model = cls._pinned_model
            text, swap_to, refused = self._run_cli(full_prompt, model)

            if swap_to and swap_to != model:
                # Session was contaminated by the retracted turn. Pin and redo.
                cls._pinned_model = swap_to
                print(f"[ClaudeCLI] model swapped mid-response -> {swap_to}; "
                      f"discarding {len(text)} chars and re-running on a clean session")
                last_reason = f"model swapped to {swap_to}"
                continue

            if refused:
                if model != cls._FALLBACK_MODEL:
                    cls._pinned_model = cls._FALLBACK_MODEL
                    print(f"[ClaudeCLI] {model or 'default model'} refused this paper; "
                          f"re-running on {cls._FALLBACK_MODEL}")
                    last_reason = f"refused by {model or 'default model'}"
                    continue
                last_reason = f"refused by {model}"
                print(f"[ClaudeCLI] {model} also refused (attempt {attempt + 1})")
                continue

            if not text:
                print(f"[ClaudeCLI] attempt {attempt + 1} returned no text "
                      f"(model={model or 'default'})")
                last_reason = "empty reply"
                continue

            if self._is_meta_reply(text):
                print(f"[ClaudeCLI] attempt {attempt + 1} returned meta-commentary "
                      f"instead of content ({len(text)} chars, model={model or 'default'})")
                last_reason = "meta-commentary reply"
                continue

            return text

        raise RuntimeError(
            f"Claude CLI produced no usable output after 3 attempts ({last_reason})"
        )


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

        if provider == "claude_cli":
            self._client = ClaudeCLIClient()
        elif provider == "claude":
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
        if provider == "claude_cli":
            return cls(provider="claude_cli")
        elif provider == "claude":
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
