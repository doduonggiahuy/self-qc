import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import BoxAnnotation, ClientProject, LabelClass, Project, Rule


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="model-qc-test-"))
class AnnotationApiTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.owner = users.objects.create_user("owner", password="test")
        self.other = users.objects.create_user("other", password="test")
        self.project = Project.objects.create(
            name="Smoke", owner=self.owner, width=640, height=480,
            fps=25, frame_count=100,
            video=SimpleUploadedFile("raw.mp4", b"raw-test-video"),
        )
        self.person = LabelClass.objects.create(
            project=self.project, name="person", prompt="human person",
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("project-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_non_owner_cannot_edit_project(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("annotate", args=[self.project.pk]))
        self.assertEqual(response.status_code, 403)

    def test_owner_can_save_manual_bbox(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("save-frame", args=[self.project.pk, 7]),
            data=json.dumps({"boxes": [{
                "id": None, "class_id": self.person.pk,
                "bbox": [10, 20, 110, 220], "status": "EDITED",
            }]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        box = BoxAnnotation.objects.get()
        self.assertEqual(box.frame_index, 7)
        self.assertEqual(box.source, "MANUAL")
        self.assertEqual(box.review_status, "EDITED")

    def test_prompt_can_be_changed(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("save-classes", args=[self.project.pk]),
            data=json.dumps({"classes": [{
                "id": self.person.pk, "name": "staff",
                "prompt": "restaurant staff uniform", "enabled": True,
                "confidence": 0.37,
            }]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.person.refresh_from_db()
        self.assertEqual(self.person.name, "staff")
        self.assertEqual(self.person.prompt, "restaurant staff uniform")
        self.assertEqual(self.person.confidence, 0.37)

        page = self.client.get(reverse("annotate", args=[self.project.pk]))
        self.assertContains(page, 'value="0.37"', count=2)
        self.assertNotContains(page, 'value="0,37"')

    def test_classes_can_be_created_and_deleted_from_annotator(self):
        BoxAnnotation.objects.create(
            project=self.project, frame_index=0, label_class=self.person,
            x1=1, y1=2, x2=3, y2=4,
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("save-classes", args=[self.project.pk]),
            data=json.dumps({
                "deleted_ids": [self.person.pk],
                "classes": [{
                    "id": None, "name": "staff", "prompt": "restaurant staff",
                    "confidence": 0.42, "enabled": True,
                }],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(LabelClass.objects.filter(pk=self.person.pk).exists())
        self.assertFalse(BoxAnnotation.objects.exists())
        self.assertTrue(self.project.classes.filter(name="staff", confidence=0.42).exists())

    def test_annotated_video_can_be_reused_by_multiple_rules(self):
        client_project = ClientProject.objects.create(name="Customer A", owner=self.owner)
        self.project.client_project = client_project
        self.project.save(update_fields=["client_project"])
        first = Rule.objects.create(client_project=client_project, name="No phone")
        second = Rule.objects.create(client_project=client_project, name="Staff uniform")
        first.videos.add(self.project)
        second.videos.add(self.project)
        self.assertEqual(self.project.rules.count(), 2)

    def test_save_empty_frame_deletes_all_bbox_on_that_frame(self):
        BoxAnnotation.objects.create(
            project=self.project, frame_index=7, label_class=self.person,
            x1=1, y1=2, x2=3, y2=4, review_status="PREDICTED",
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("save-frame", args=[self.project.pk, 7]),
            data=json.dumps({"boxes": []}), content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BoxAnnotation.objects.filter(frame_index=7).exists())

    def test_export_contains_only_reviewed_boxes(self):
        BoxAnnotation.objects.create(
            project=self.project, frame_index=2, label_class=self.person,
            x1=1, y1=2, x2=3, y2=4, review_status="APPROVED",
        )
        BoxAnnotation.objects.create(
            project=self.project, frame_index=3, label_class=self.person,
            x1=1, y1=2, x2=3, y2=4, review_status="PREDICTED",
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("export-jsonl", args=[self.project.pk]))
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content).decode()
        self.assertIn('"frame_index": 2', body)
        self.assertNotIn('"frame_index": 3', body)
        self.assertEqual(len(response["X-Video-SHA256"]), 64)
