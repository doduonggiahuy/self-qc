from celery import shared_task

from .models import RuleRun


@shared_task(queue="ai_rules")
def execute_rule_run(run_pk):
    """Execution seam for the future rule engine/worker."""
    run = RuleRun.objects.get(pk=run_pk)
    run.status = "FAILED"
    run.error = "AI Rule executor chưa được cấu hình."
    run.save(update_fields=["status", "error"])
    return {"status": run.status, "run_id": run.pk}
