from django.core.management.base import BaseCommand

from annotations.roles import ensure_annotation_roles


class Command(BaseCommand):
    def handle(self, *args, **options):
        ensure_annotation_roles()
        self.stdout.write(self.style.SUCCESS("QC roles are ready"))
