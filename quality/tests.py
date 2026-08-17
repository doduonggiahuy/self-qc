import tempfile
import io
import zipfile
from unittest.mock import patch
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from annotations.models import BoxAnnotation, ClientProject, LabelClass, Project
from .models import EvaluationDataset, EvaluationDatasetClass, EvaluationModel, GroundTruthRelease, InferenceModel, ModelEvaluationFrame, ModelEvaluationRun, TestCase as QualityTestCase, TestRun
from .services import create_run, execute_run, freeze_ground_truth


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="model-qc-quality-test-"), DATASET_ROOT=tempfile.mkdtemp(prefix="model-qc-dataset-test-"))
class QualityFlowTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.owner = users.objects.create_user("quality-owner", password="test")
        self.other = users.objects.create_user("quality-other", password="test")
        self.client_project = ClientProject.objects.create(name="Quality Customer", owner=self.owner)
        self.project = Project.objects.create(
            name="Quality", client_project=self.client_project, owner=self.owner, width=640, height=480, fps=25,
            frame_count=100, coverage="exhaustive",
            video=SimpleUploadedFile("raw.mp4", b"immutable-video"),
        )
        self.label = LabelClass.objects.create(project=self.project, name="person", prompt="person")
        self.box = BoxAnnotation.objects.create(
            project=self.project, frame_index=10, label_class=self.label,
            x1=1, y1=2, x2=30, y2=40, review_status="APPROVED",
        )

    def test_freeze_creates_immutable_snapshot_of_reviewed_boxes(self):
        release = freeze_ground_truth(self.project, self.owner)
        item = release.items.get()
        self.assertEqual(release.annotation_count, 1)
        self.assertEqual(item.payload["bbox"], [1, 2, 30, 40])
        self.box.x2 = 999
        self.box.save(update_fields=["x2"])
        item.refresh_from_db()
        self.assertEqual(item.payload["bbox"], [1, 2, 30, 40])

    def test_gt_validation_run_passes(self):
        release = freeze_ground_truth(self.project, self.owner)
        case = QualityTestCase.objects.create(
            project=self.project, name="GT readiness", ground_truth_release=release,
            assertions=[{"metric": "annotation_count", "operator": ">=", "value": 1}],
            created_by=self.owner,
        )
        run = execute_run(create_run(case, self.owner))
        self.assertEqual(run.status, "PASSED")
        self.assertEqual(run.metrics["annotation_count"], 1)
        self.assertTrue(run.assertion_results[0]["passed"])
        self.assertEqual(run.input_snapshot["gt_version"], 1)

    def test_gt_validation_run_can_fail_assertion(self):
        release = freeze_ground_truth(self.project, self.owner)
        case = QualityTestCase.objects.create(
            project=self.project, name="Strict GT", ground_truth_release=release,
            assertions=[{"metric": "annotation_count", "operator": ">=", "value": 2}],
            created_by=self.owner,
        )
        run = execute_run(create_run(case, self.owner))
        self.assertEqual(run.status, "FAILED")

    def test_non_owner_cannot_open_quality_dashboard(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("quality-dashboard", args=[self.project.pk]))
        self.assertEqual(response.status_code, 403)

    def test_owner_can_render_quality_dashboard(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("quality-dashboard", args=[self.project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quality Lab")

    def test_authenticated_user_can_open_model_quality_workspace(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("model-quality-workspace"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Evaluation tasks")
        self.assertContains(response, "+ Tạo evaluation task")
        self.assertContains(response, self.client_project.name)

    def test_authenticated_user_can_open_model_quality_create_wizard(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("model-quality-create"), {"project": self.client_project.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload evaluation dataset")
        self.assertContains(response, "Class mapping")
        self.assertContains(response, "Customer project")
        self.assertContains(response, self.client_project.name)

    def test_model_quality_workspace_requires_login(self):
        response = self.client.get(reverse("model-quality-workspace"))
        self.assertEqual(response.status_code, 302)

    def test_chunked_dataset_is_linked_to_customer_project(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("model-quality-upload-init"), {
            "name": "Rule evaluation", "source_kind": "FOLDER",
            "client_project_id": self.client_project.pk,
        })
        self.assertEqual(response.status_code, 201, response.content)
        dataset = EvaluationDataset.objects.get(pk=response.json()["id"])
        self.assertEqual(dataset.client_project, self.client_project)

    def test_owner_can_edit_model_quality_task(self):
        dataset = EvaluationDataset.objects.create(
            name="Before", owner=self.owner, client_project=self.client_project,
            source_kind="FOLDER", source_path="ready", status="READY",
        )
        self.client.force_login(self.owner)
        response = self.client.post(reverse("model-quality-task-edit", args=[dataset.pk]), {
            "name": "After", "client_project": self.client_project.pk,
        })
        self.assertRedirects(response, reverse("model-quality-workspace"))
        dataset.refresh_from_db()
        self.assertEqual(dataset.name, "After")

    def test_owner_can_delete_task_and_dataset_artifacts(self):
        artifact = Path(settings.DATASET_ROOT) / "delete-task" / "content"
        artifact.mkdir(parents=True)
        (artifact / "sample.jpg").write_bytes(b"image")
        dataset = EvaluationDataset.objects.create(
            name="Delete me", owner=self.owner, client_project=self.client_project,
            source_kind="FOLDER", source_path="delete-task/content", status="READY",
        )
        self.client.force_login(self.owner)
        response = self.client.post(reverse("model-quality-task-delete", args=[dataset.pk]))
        self.assertRedirects(response, reverse("model-quality-workspace"))
        self.assertFalse(EvaluationDataset.objects.filter(pk=dataset.pk).exists())
        self.assertFalse(artifact.parent.exists())

    def test_yolo_zip_is_uploaded_inspected_and_persisted(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("dataset/data.yaml", "names: [person, dining_table]\n")
            archive.writestr("dataset/images/train/a.jpg", b"not-decoded-during-inspection")
            archive.writestr("dataset/labels/train/a.txt", "0 0.5 0.5 0.2 0.3\n1 0.2 0.2 0.1 0.1\n")
        self.client.force_login(self.owner)
        response = self.client.post(reverse("model-quality-dataset-upload"), data={
            "name": "YOLO validation", "source_kind": "ZIP",
            "files": SimpleUploadedFile("dataset.zip", payload.getvalue(), content_type="application/zip"),
        })
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["format"], "YOLO")
        self.assertEqual(data["task"], "DETECTION")
        self.assertEqual(data["image_count"], 1)
        self.assertEqual(data["annotation_count"], 2)
        self.assertEqual([item["name"] for item in data["classes"]], ["person", "dining_table"])

    def test_dataset_zip_rejects_path_traversal(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("../escape.jpg", b"unsafe")
        self.client.force_login(self.owner)
        response = self.client.post(reverse("model-quality-dataset-upload"), data={
            "name": "Unsafe", "source_kind": "ZIP",
            "files": SimpleUploadedFile("unsafe.zip", payload.getvalue(), content_type="application/zip"),
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("không an toàn", response.json()["error"])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_chunked_zip_upload_is_reassembled_and_processed(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("data.yaml", "names: [person]\n")
            archive.writestr("images/a.jpg", b"image")
            archive.writestr("labels/a.txt", "0 0.5 0.5 0.2 0.2\n")
        raw = payload.getvalue()
        self.client.force_login(self.owner)
        started = self.client.post(reverse("model-quality-upload-init"), {
            "name": "Chunked ZIP", "source_kind": "ZIP", "client_project_id": self.client_project.pk,
        })
        self.assertEqual(started.status_code, 201)
        dataset_id = started.json()["id"]
        midpoint = len(raw) // 2
        for index, part in enumerate((raw[:midpoint], raw[midpoint:])):
            response = self.client.post(reverse("model-quality-upload-chunk", args=[dataset_id]), {
                "chunk_index": index,
                "files": SimpleUploadedFile("dataset.zip", part),
            })
            self.assertEqual(response.status_code, 200, response.content)
        with self.captureOnCommitCallbacks(execute=True):
            finalized = self.client.post(reverse("model-quality-upload-finalize", args=[dataset_id]))
        self.assertEqual(finalized.status_code, 202, finalized.content)
        status = self.client.get(reverse("model-quality-upload-status", args=[dataset_id])).json()
        self.assertEqual(status["status"], "READY")
        self.assertEqual(status["annotation_count"], 1)

    def test_chunk_retry_is_idempotent(self):
        self.client.force_login(self.owner)
        started = self.client.post(reverse("model-quality-upload-init"), {
            "name": "Retry folder", "source_kind": "FOLDER", "client_project_id": self.client_project.pk,
        })
        dataset_id = started.json()["id"]
        url = reverse("model-quality-upload-chunk", args=[dataset_id])
        payload = {
            "chunk_index": 0, "paths": ["images/a.jpg"],
            "files": SimpleUploadedFile("a.jpg", b"image"),
        }
        first = self.client.post(url, payload)
        retry = self.client.post(url, {
            "chunk_index": 0, "paths": ["images/a.jpg"],
            "files": SimpleUploadedFile("a.jpg", b"image"),
        })
        self.assertEqual(first.status_code, 200)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["next_chunk"], 1)

    def test_model_upload_is_queued_for_metadata_analysis(self):
        dataset = EvaluationDataset.objects.create(
            name="Ready", owner=self.owner, source_kind="FOLDER", source_path="ready", status="READY"
        )
        self.client.force_login(self.owner)
        with patch("quality.tasks.analyze_evaluation_model.delay") as delay, self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("model-quality-model-upload", args=[dataset.pk]), {
                "model_file": SimpleUploadedFile("model.onnx", b"onnx"),
            })
        self.assertEqual(response.status_code, 202, response.content)
        model = EvaluationModel.objects.get(pk=response.json()["id"])
        self.assertEqual(model.status, "ANALYZING")
        delay.assert_called_once_with(model.pk)

    def test_owner_can_delete_failed_or_unused_evaluation_model(self):
        dataset = EvaluationDataset.objects.create(
            name="Ready", owner=self.owner, client_project=self.client_project,
            source_kind="FOLDER", source_path="ready", status="READY",
        )
        model = EvaluationModel.objects.create(
            dataset=dataset, owner=self.owner, name="retry", status="ERROR",
            model_file=SimpleUploadedFile("retry.onnx", b"onnx"), error="invalid",
        )
        self.client.force_login(self.owner)
        response = self.client.post(reverse("model-quality-model-delete", args=[model.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(EvaluationModel.objects.filter(pk=model.pk).exists())

    def test_model_class_mapping_uses_model_to_gt_direction(self):
        dataset = EvaluationDataset.objects.create(
            name="Ready", owner=self.owner, source_kind="FOLDER", source_path="ready", status="READY"
        )
        EvaluationDatasetClass.objects.create(dataset=dataset, external_id="0", name="dining_table", annotation_count=4)
        model = EvaluationModel.objects.create(
            dataset=dataset, owner=self.owner, name="detector", status="READY",
            model_file=SimpleUploadedFile("model.onnx", b"onnx"), model_classes=["table", "person"],
        )
        self.client.force_login(self.owner)
        response = self.client.post(reverse("model-quality-model-mapping", args=[model.pk]), {
            "gt_classes": '[{"id":"0","name":"dining_table"}]',
            "class_mapping": '{"table":"dining_table","person":null}',
        })
        self.assertEqual(response.status_code, 200, response.content)
        model.refresh_from_db()
        self.assertEqual(model.class_mapping, {"table": "dining_table", "person": None})

    def test_run_status_exposes_secured_live_preview_image(self):
        source = Path(settings.DATASET_ROOT) / "preview-dataset"
        (source / "images").mkdir(parents=True)
        (source / "images/frame.jpg").write_bytes(b"preview-image")
        dataset = EvaluationDataset.objects.create(
            name="Preview", owner=self.owner, source_kind="FOLDER",
            source_path="preview-dataset", status="READY",
        )
        model = EvaluationModel.objects.create(
            dataset=dataset, owner=self.owner, name="detector", status="READY",
            model_file=SimpleUploadedFile("model.onnx", b"onnx"), model_classes=["person"],
            class_mapping={"person": "person"},
        )
        run = ModelEvaluationRun.objects.create(
            dataset=dataset, model=model, owner=self.owner, progress_current=1,
            progress_total=2, preview={"image": "images/frame.jpg", "predictions": []},
        )
        ModelEvaluationFrame.objects.create(
            run=run, frame_index=0, image="images/frame.jpg",
            output={"image": "images/frame.jpg", "kind": "detection", "predictions": []},
        )
        self.client.force_login(self.owner)
        status = self.client.get(reverse("model-quality-run-status", args=[run.pk]))
        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.json()["preview_image_url"])
        image = self.client.get(reverse("model-quality-run-preview-image", args=[run.pk]))
        self.assertEqual(image.status_code, 200)
        self.assertEqual(b"".join(image.streaming_content), b"preview-image")
        viewer = self.client.get(reverse("model-quality-run-viewer", args=[run.pk]))
        self.assertEqual(viewer.status_code, 200)
        self.assertContains(viewer, "Inference progress")
        frame = self.client.get(reverse("model-quality-run-frame-data", args=[run.pk, 0]))
        self.assertEqual(frame.status_code, 200)
        self.assertEqual(frame.json()["frame_index"], 0)
        exported = self.client.get(reverse("model-quality-run-export", args=[run.pk]))
        exported_body = b"".join(exported.streaming_content).decode()
        self.assertIn('"type": "summary"', exported_body)
        self.assertIn('"type": "frame"', exported_body)
        self.client.force_login(self.other)
        denied = self.client.get(reverse("model-quality-run-preview-image", args=[run.pk]))
        self.assertEqual(denied.status_code, 404)

    def test_annotator_brand_links_to_workspace_root(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("annotate", args=[self.project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="brand" href="/"')
        self.assertContains(response, "MODEL QC STUDIO")

    def test_regular_user_cannot_open_system_registry(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("quality-system-models"))
        self.assertEqual(response.status_code, 403)

    def test_admin_console_is_staff_only(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("quality-system-dashboard")).status_code, 403)
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        response = self.client.get(reverse("quality-system-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin Console")

    def test_users_can_select_enabled_model_independently(self):
        model = InferenceModel.objects.create(
            key="yolo-world-m", name="YOLO-World M", task="OPEN_VOCAB_DETECTION",
            model_file=SimpleUploadedFile("yolov8m-worldv2.pt", b"fake-weight"), adapter="quality.adapters.YoloWorldAdapter",
            enabled=True, status="READY",
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("quality-select-inference-model"),
            data='{"model_id": %s}' % model.pk,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.inference_preference.model, model)
        self.assertFalse(hasattr(self.other, "inference_preference"))
        model.model_file.delete(save=False)

    def test_user_cannot_select_disabled_or_unsupported_model(self):
        model = InferenceModel.objects.create(
            key="onnx-model", name="ONNX", task="OPEN_VOCAB_DETECTION",
            model_file=SimpleUploadedFile("model.onnx", b"fake-onnx"), adapter="quality.adapters.YoloWorldAdapter", enabled=True,
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("quality-select-inference-model"), data='{"model_id": %s}' % model.pk,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        model.model_file.delete(save=False)

    def test_staff_can_delete_model_registry_record(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        model = InferenceModel.objects.create(
            key="delete-me", name="Delete me", task="OPEN_VOCAB_DETECTION",
            model_file="registry/delete.pt", adapter="quality.adapters.YoloWorldAdapter",
        )
        self.client.force_login(self.owner)
        response = self.client.post(reverse("quality-system-model-delete", args=[model.pk]))
        self.assertRedirects(response, reverse("quality-system-models"))
        self.assertFalse(InferenceModel.objects.filter(pk=model.pk).exists())

    def test_staff_can_retry_failed_registry_model(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        model = InferenceModel.objects.create(
            key="retry-local", name="retry-local", provider="LOCAL", model_file="registry/retry.pt",
            task="OPEN_VOCAB_DETECTION", adapter="quality.adapters.YoloWorldAdapter",
            status="ERROR", enabled=False, validation_error="model validation failed",
        )
        self.client.force_login(self.owner)
        def ready(item):
            item.status, item.enabled, item.validation_error = "READY", True, ""
            item.save(update_fields=["status", "enabled", "validation_error"])
            return item
        with patch("quality.views.provision_model", side_effect=ready) as provision:
            response = self.client.post(reverse("quality-system-model-retry", args=[model.pk]))
        self.assertRedirects(response, reverse("quality-system-models"))
        provision.assert_called_once()
        model.refresh_from_db()
        self.assertEqual(model.status, "READY")

    def test_staff_user_can_register_inference_model(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        self.client.force_login(self.owner)
        response = self.client.post(reverse("quality-system-models"), data={
            "provider": "LOCAL",
            "model_file": SimpleUploadedFile("custom.pt", b"fake-weight"),
            "enabled": "on",
        })
        self.assertRedirects(response, reverse("quality-system-models"))
        model = InferenceModel.objects.get(name="custom")
        self.assertTrue(model.enabled)
        model.model_file.delete(save=False)

    def test_system_registry_tolerates_legacy_record_without_file(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        InferenceModel.objects.create(
            key="legacy", name="Legacy", task="OPEN_VOCAB_DETECTION",
            model_file="", adapter="quality.adapters.YoloWorldAdapter", enabled=True,
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("quality-system-models"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PENDING")

    def test_staff_can_upload_valid_model_bundle(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("config.json", "{}")
            archive.writestr("preprocessor_config.json", "{}")
            archive.writestr("model.safetensors", b"safe")
        self.client.force_login(self.owner)
        response = self.client.post(reverse("quality-system-models"), data={
            "provider": "LOCAL",
            "model_file": SimpleUploadedFile("florence.zip", payload.getvalue()),
            "enabled": "on",
        })
        self.assertRedirects(response, reverse("quality-system-models"))
        model = InferenceModel.objects.get(name="florence")
        self.assertEqual(model.artifact_type, "MODEL_BUNDLE")
        self.assertTrue(model.is_selectable)
        from .model_artifacts import remove_artifact
        remove_artifact(model)

    def test_bundle_upload_rejects_path_traversal(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("../escape.txt", "unsafe")
        self.client.force_login(self.owner)
        response = self.client.post(reverse("quality-system-models"), data={
            "provider": "LOCAL",
            "model_file": SimpleUploadedFile("unsafe.zip", payload.getvalue()),
        })
        self.assertRedirects(response, reverse("quality-system-models"))
        self.assertEqual(InferenceModel.objects.get(name="unsafe").status, "ERROR")

    def test_admin_upload_rejects_unsupported_extension(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        self.client.force_login(self.owner)
        response = self.client.post(reverse("quality-system-models"), data={
            "key": "bad", "name": "Bad", "task": "OPEN_VOCAB_DETECTION",
            "model_file": SimpleUploadedFile("bad.exe", b"bad"),
            "adapter": "quality.adapters.UnavailableAdapter", "default_config": "{}",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(InferenceModel.objects.filter(key="bad").exists())

    def test_owner_can_run_case_through_web_flow(self):
        release = freeze_ground_truth(self.project, self.owner)
        case = QualityTestCase.objects.create(
            project=self.project, name="Web GT", ground_truth_release=release,
            assertions=[], created_by=self.owner,
        )
        self.client.force_login(self.owner)
        response = self.client.post(reverse("quality-run-case", args=[self.project.pk, case.pk]))
        run = TestRun.objects.get()
        self.assertRedirects(response, reverse("quality-run-detail", args=[self.project.pk, run.pk]))
        self.assertEqual(run.status, "PASSED")
