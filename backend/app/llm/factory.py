"""Model-agnostic chat model construction.

Agents never import a provider package. They ask for a model here and get a
LangChain `BaseChatModel`; swapping Gemini for OpenAI/Anthropic is a config change.
"""

from typing import Optional, Type, TypeVar

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from app.core.config import settings

T = TypeVar("T", bound=BaseModel)

_API_KEYS = {
    "google_genai": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def get_chat_model(
    model: Optional[str] = None,
    provider: Optional[str] = None,
    temperature: Optional[float] = None,
    **kwargs,
) -> BaseChatModel:
    provider = provider or settings.LLM_PROVIDER
    kwargs.setdefault(
        "temperature",
        settings.LLM_TEMPERATURE if temperature is None else temperature,
    )
    key_attr = _API_KEYS.get(provider)
    if key_attr and getattr(settings, key_attr):
        kwargs.setdefault("api_key", getattr(settings, key_attr))
    return init_chat_model(
        model or settings.LLM_MODEL, model_provider=provider, **kwargs
    )


def structured_model(schema: Type[T], **kwargs):
    """Chat model that returns a validated `schema` instance (no manual JSON parsing)."""
    return get_chat_model(**kwargs).with_structured_output(schema)
