from celery import shared_task

from .models import ServiceProvisioning


@shared_task(queue="platform")
def mark_provisioning_requested(provisioning_pk, event_id):
    """Platform queue seam for future Kafka/API provisioning dispatch."""
    state = ServiceProvisioning.objects.get(pk=provisioning_pk)
    state.status = "PROVISIONING"
    state.last_event_id = event_id
    state.save(update_fields=["status", "last_event_id", "updated_at"])
    return {"provisioning_id": state.pk, "status": state.status}
