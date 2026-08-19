"""Training-owned boundary for model artifacts.

Database tables still live in ``quality`` during the transitional monolith.
Import this module in new code so the eventual migration is localized.
"""

from model_registry import InferenceModel, UserInferencePreference
from model_registry.services import get_enabled_model

__all__ = ["InferenceModel", "UserInferencePreference", "get_enabled_model"]
