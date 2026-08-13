from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options):
        annotator, _ = Group.objects.get_or_create(name="QC Annotator")
        reviewer, _ = Group.objects.get_or_create(name="QC Reviewer")
        base = Permission.objects.filter(content_type__app_label="annotations", codename__in=[
            "add_project", "view_project", "change_project", "view_labelclass", "add_labelclass",
            "change_labelclass", "view_boxannotation", "add_boxannotation", "change_boxannotation", "delete_boxannotation",
        ])
        annotator.permissions.set(base)
        reviewer.permissions.set(base | Permission.objects.filter(content_type__app_label="annotations", codename__in=["edit_all_projects", "review_annotations"]))
        self.stdout.write(self.style.SUCCESS("QC roles are ready"))

