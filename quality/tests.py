import tempfile
import io
import zipfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from annotations.models import BoxAnnotation, LabelClass, Project
from .models import GroundTruthRelease, InferenceModel, TestCase as QualityTestCase, TestRun
from .services import create_run, execute_run, freeze_ground_truth


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="model-qc-quality-test-"))
class QualityFlowTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.owner = users.objects.create_user("quality-owner", password="test")
        self.other = users.objects.create_user("quality-other", password="test")
        self.project = Project.objects.create(
            name="Quality", owner=self.owner, width=640, height=480, fps=25,
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
