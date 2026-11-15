"""Anthropic Claude model selection and standard API pricing used by this tool."""

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple


DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_VISION_SELECT_MODEL = "claude-haiku-5-5"


@dataclass(frozen=True)
class ModelPricing:
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float


# Standard processing prices in USD per 1M tokens.
# Keep snapshot resolution separate so aliases and dated snapshots share a rate.
MODEL_PRICING = {
    "claude-sonnet-5-5": ModelPricing(2.00, 0.10, 10.00),
    "claude-haiku-5-5": ModelPricing(0.10, 0.01, 0.50),
    "claude-opus-5-5": ModelPricing(4.00, 0.20, 20.00),
}


def resolve_models(environ: Mapping[str, str]) -> Tuple[str, str, str]:
    """Return auxiliary, Stage 1, and Stage 2 models.

    Auxiliary calls follow Stage 1 unless ANTHROPIC_MODEL explicitly overrides them.
    This keeps title/description/highlight processing aligned with the main model
    configured by the existing bat files.
    """
    general = environ.get("ANTHROPIC_MODEL")
    stage1 = environ.get("ANTHROPIC_MODEL_STAGE1") or general or DEFAULT_MODEL
    stage2 = environ.get("ANTHROPIC_MODEL_STAGE2") or general or stage1
    auxiliary = general or stage1
    return auxiliary, stage1, stage2


def resolve_vision_select_model(environ: Mapping[str, str]) -> str:
    """Return the model used for vision frame selection (cheap model by default)."""
    return environ.get("ANTHROPIC_MODEL_VISION_SELECT") or DEFAULT_VISION_SELECT_MODEL


def get_model_pricing(model: str) -> Optional[ModelPricing]:
    """Resolve an alias or dated snapshot to its standard token prices."""
    for base_model in sorted(MODEL_PRICING, key=len, reverse=True):
        if model == base_model or model.startswith(base_model + "-"):
            return MODEL_PRICING[base_model]
    return None


def calculate_usage_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> Optional[float]:
    """Calculate the standard API cost in USD, or None for an unknown model."""
    pricing = get_model_pricing(model)
    if pricing is None:
        return None

    cached_input_tokens = min(max(cached_input_tokens, 0), input_tokens)
    uncached_input_tokens = input_tokens - cached_input_tokens
    return (
        uncached_input_tokens * pricing.input_per_million
        + cached_input_tokens * pricing.cached_input_per_million
        + output_tokens * pricing.output_per_million
    ) / 1_000_000
