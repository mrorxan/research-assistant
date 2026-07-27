"""Multi-provider failover for the LLM synthesis step.

FailoverLLM implements the provided LLMProvider contract, so it plugs
straight into ai.synthesize(llm=...) without touching the ai/ package.
Providers are built lazily: the fallback SDK and API key are only needed if
the primary actually fails.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from ai.providers.base import LLMProvider, ProviderError
from researcher.config import Settings

logger = logging.getLogger(__name__)

ProviderFactory = Callable[[], LLMProvider]

def _concrete_factory(provider: str, model: str | None) -> ProviderFactory:
    name = provider.lower().strip()

    def build() -> LLMProvider:
        if name == "anthropic":
            from ai.providers.anthropic import AnthropicLLM
            return AnthropicLLM(model)
        if name == "openai":
            from ai.providers.openai import OpenAILLM
            return OpenAILLM(model)
        if name in ("google", "gemini"):
            from ai.providers.google import GeminiLLM
            return GeminiLLM(model)
        raise ProviderError(f"Unknown LLM provider {provider!r}")

    return build

class FailoverLLM(LLMProvider):
    """Tries each configured provider in order until one answers."""

    def __init__(self, factories: Sequence[tuple[str, ProviderFactory]]) -> None:
        if not factories:
            raise ValueError("at least one provider factory is required")
        self._factories = list(factories)
        self._instances: dict[str, LLMProvider] = {}

    def complete(
        self,
        prompt: str,
        *,
        json_schema: dict | None = None,
        max_tokens: int = 1024,
    ) -> str:
        last_error: ProviderError | None = None
        for name, factory in self._factories:
            try:
                provider = self._instances.get(name)
                if provider is None:
                    provider = factory()
                    self._instances[name] = provider
                return provider.complete(prompt, json_schema=json_schema, max_tokens=max_tokens)
            except ProviderError as exc:
                logger.warning("llm_provider_failed name=%s error=%s", name, exc)
                last_error = exc
        raise ProviderError(f"all LLM providers failed; last error: {last_error}")

def build_llm(settings: Settings) -> LLMProvider | None:
    """Build the LLM for synthesis, or None to let ai/ pick its default.

    Without a configured fallback we return None so ai.synthesize uses its
    own factory, exactly as a project without this bonus would.
    """
    fallback = settings.llm_fallback_provider.strip()
    if not fallback:
        return None
    chain = [
        (settings.llm_provider, _concrete_factory(settings.llm_provider, settings.llm_model)),
        (fallback, _concrete_factory(fallback, settings.llm_fallback_model or None)),
    ]
    logger.info("llm_failover_enabled chain=%s", [name for name, _ in chain])
    return FailoverLLM(chain)
