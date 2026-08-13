import zipfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Pack a Hugging Face model directory into a registry-compatible ZIP."

    def add_arguments(self, parser):
        parser.add_argument("source")
        parser.add_argument("output")

    def handle(self, source, output, **options):
        source_path = Path(source).resolve()
        output_path = Path(output).resolve()
        if not source_path.is_dir():
            raise CommandError(f"Không tìm thấy model directory: {source_path}")
        required = {"config.json", "model.safetensors", "preprocessor_config.json"}
        missing = required - {item.name for item in source_path.iterdir() if item.is_file()}
        if missing:
            raise CommandError(f"Model directory thiếu: {', '.join(sorted(missing))}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            for item in sorted(source_path.rglob("*")):
                if item.is_file() and ".cache" not in item.parts and item.name not in {"pytorch_model.bin", ".gitattributes"}:
                    archive.write(item, item.relative_to(source_path))
        self.stdout.write(self.style.SUCCESS(f"Bundle ready: {output_path} ({output_path.stat().st_size} bytes)"))
