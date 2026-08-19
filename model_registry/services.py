"""Compatibility service for model registry use cases."""

from quality.models import InferenceModel


def get_enabled_model(model_pk=None):
    """Resolve a selectable model without exposing ORM access to callers."""
    queryset = InferenceModel.objects.filter(enabled=True, status="READY")
    return queryset.filter(pk=model_pk).first() if model_pk else queryset.first()
