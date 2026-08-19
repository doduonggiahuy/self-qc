"""Model artifact registry boundary.

The persisted model is still temporarily implemented by ``quality`` for
backward compatibility. New consumers should depend on this boundary rather
than importing ``quality.models.InferenceModel`` directly.
"""

from quality.models import InferenceModel, UserInferencePreference

__all__ = ["InferenceModel", "UserInferencePreference"]
