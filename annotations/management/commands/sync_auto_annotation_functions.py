import json
from urllib.request import urlopen

from django.core.management.base import BaseCommand, CommandError

from annotations.models import AutoAnnotationFunction


FUNCTIONS = [
    {"key": "yolo26s-detection", "name": "YOLO26s Detection", "kind": "detector", "endpoint_url": "http://annotation-yolo26-detection:8080/infer", "spec_url": "http://annotation-yolo26-detection:8080/spec"},
    {"key": "yolo26s-pose", "name": "YOLO26s Pose", "kind": "pose", "endpoint_url": "http://annotation-yolo26-pose:8080/infer", "spec_url": "http://annotation-yolo26-pose:8080/spec"},
]


class Command(BaseCommand):
    help = "Discover built-in auto annotation services and synchronize their label specs."

    def handle(self, *args, **options):
        for definition in FUNCTIONS:
            try:
                with urlopen(definition["spec_url"], timeout=30) as response:
                    spec = json.loads(response.read().decode("utf-8"))
            except Exception as exc:
                raise CommandError(f'Cannot discover {definition["name"]}: {exc}') from exc
            function, created = AutoAnnotationFunction.objects.update_or_create(
                key=definition["key"],
                defaults={"name": definition["name"], "kind": definition["kind"], "endpoint_url": definition["endpoint_url"], "spec": spec, "enabled": True, "timeout_seconds": 120},
            )
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action} {function.name}: {len(spec)} labels"))
