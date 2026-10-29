"""ScamShield AI — offline job-scam detection."""

from .engine import (
    Analysis,
    Flag,
    analyze,
    engine_online,
    list_models,
    load_skill,
    pick_model,
)

__version__ = "1.0.0"
__all__ = [
    "Analysis",
    "Flag",
    "analyze",
    "engine_online",
    "list_models",
    "load_skill",
    "pick_model",
]
