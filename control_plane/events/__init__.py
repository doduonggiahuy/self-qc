"""Versioned event envelope shared by the monolith and future services."""


def envelope(event_type, aggregate_id, payload, *, event_id=None, version=1, producer="freeflow"):
    import uuid
    from django.utils import timezone

    return {
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": version,
        "occurred_at": timezone.now().isoformat(),
        "producer": producer,
        "aggregate_id": str(aggregate_id),
        "payload": payload,
    }
