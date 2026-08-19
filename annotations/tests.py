import json
import io
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import AnnotationJob, AnnotationShape, AnnotationTask, AutoAnnotationFunction, AutoAnnotationRun, BoxAnnotation, ClientProject, LabelClass, Project, Rule
from control_plane.projects.roles import ensure_platform_roles


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="model-qc-test-"))
class AnnotationApiTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.owner = users.objects.create_superuser("owner", password="test")
        self.other = users.objects.create_user("other", password="test")
        self.project = Project.objects.create(
            name="Smoke", owner=self.owner, width=640, height=480,
            fps=25, frame_count=100,
            video=SimpleUploadedFile("raw.mp4", b"raw-test-video"),
        )
        self.person = LabelClass.objects.create(
            project=self.project, name="person",
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("project-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_root_creates_project_with_labels_attributes_skeleton_and_rules(self):
        self.client.force_login(self.owner)
        page = self.client.get(reverse("client-project-create"))
        self.assertContains(page, "Tạo Annotation Project")
        labels = [{
            "name": "person_pose", "type": "skeleton",
            "attributes": [{"name": "occluded", "input_type": "checkbox", "values": ["false"]}],
            "points": [{"name": "nose", "x": 50, "y": 20}, {"name": "neck", "x": 50, "y": 40}],
            "edges": [{"from": "nose", "to": "neck"}],
        }]
        response = self.client.post(reverse("client-project-create"), {
            "name": "Furama", "description": "Resort", "labels_schema": json.dumps(labels),
            "rules_schema": json.dumps([{"name": "use_phone", "description": "Phone usage"}]),
        })
        project = ClientProject.objects.get(name="Furama")
        self.assertRedirects(response, reverse("client-project-detail", args=[project.pk]))
        label = project.labels.get(name="person_pose")
        self.assertEqual(label.label_type, "skeleton")
        self.assertEqual(label.attributes.get().name, "occluded")
        self.assertEqual(label.skeleton_points.count(), 2)
        self.assertEqual(label.skeleton_points.values("color").distinct().count(), 2)
        self.assertEqual(label.skeleton_edges.count(), 1)
        self.assertTrue(project.rules.filter(name="use_phone").exists())

    def test_root_can_paste_cvat_raw_labels_with_colors_attributes_and_skeleton_svg(self):
        self.client.force_login(self.owner)
        labels = [
            {"name": "person", "id": 8253792, "color": "#00c900", "type": "any", "attributes": [{"id": 2597052, "name": "phone_relation", "input_type": "select", "mutable": False, "values": ["no_phone", "holding"], "default_value": "no_phone"}]},
            {"name": "person_pose", "id": 8253807, "color": "#3d3df5", "type": "skeleton", "sublabels": [
                {"name": "nose", "type": "points", "color": "#4dc8fc", "id": 8253808, "attributes": []},
                {"name": "neck", "type": "points", "color": "#17b183", "id": 8253809, "attributes": []},
            ], "svg": '<line data-type="edge" data-node-from="1" data-node-to="2"></line><circle cx="48" cy="21" data-node-id="1" data-label-id="8253808"></circle><circle cx="50" cy="40" data-node-id="2" data-label-id="8253809"></circle>', "attributes": []},
        ]
        response = self.client.post(reverse("client-project-create"), {"name": "CVAT Import", "labels_schema": json.dumps(labels), "rules_schema": "[]"})
        project = ClientProject.objects.get(name="CVAT Import")
        self.assertRedirects(response, reverse("client-project-detail", args=[project.pk]))
        person = project.labels.get(name="person")
        self.assertEqual((person.label_type, person.color), ("rectangle", "#00c900"))
        self.assertEqual(person.attributes.get().default_value, "no_phone")
        pose = project.labels.get(name="person_pose")
        self.assertEqual(pose.color, "#3d3df5")
        self.assertEqual(list(pose.skeleton_points.values_list("name", flat=True)), ["nose", "neck"])
        self.assertEqual(list(pose.skeleton_points.values_list("color", flat=True)), ["#4dc8fc", "#17b183"])
        self.assertEqual(pose.skeleton_edges.count(), 1)

    def test_data_annotator_cannot_create_project_schema(self):
        roles = ensure_platform_roles()
        self.other.groups.add(roles["DATA_ANNOTATOR"])
        self.client.force_login(self.other)
        response = self.client.post(reverse("client-project-create"), {
            "name": "Forbidden", "labels_schema": "[]", "rules_schema": "[]",
        })
        self.assertEqual(response.status_code, 403)

    def test_workspace_modules_use_named_routes(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("project-list"))
        self.assertContains(response, f'href="{reverse("annotation-task-list")}"')
        self.assertContains(response, f'href="{reverse("model-quality-workspace")}"')

    def test_ground_truth_studio_lists_accessible_videos(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("ground-truth-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.name)
        self.assertContains(response, reverse("annotation-task-list"))
        self.assertNotContains(response, reverse("annotate", args=[self.project.pk]))

    def test_legacy_prompt_annotator_is_removed(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("annotate", args=[self.project.pk])).status_code, 404)

    def test_non_owner_cannot_edit_project(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("annotate", args=[self.project.pk]))
        self.assertEqual(response.status_code, 403)

    def test_data_annotator_can_view_shared_project_and_annotate(self):
        roles = ensure_platform_roles()
        self.other.groups.add(roles["DATA_ANNOTATOR"])
        client_project = ClientProject.objects.create(name="Shared", owner=self.owner)
        self.project.client_project = client_project
        self.project.save(update_fields=["client_project"])
        task = AnnotationTask.objects.create(name="Label lobby", client_project=client_project, created_by=self.owner)
        task.assignees.add(self.other)
        self.project.annotation_task = task
        self.project.save(update_fields=["annotation_task"])
        self.client.force_login(self.other)
        self.assertContains(self.client.get(reverse("project-list")), client_project.name)
        job = AnnotationJob.objects.create(task=task, video=self.project, assignee=self.other, stop_frame=99)
        response = self.client.get(reverse("annotate", args=[self.project.pk]))
        self.assertRedirects(response, reverse("annotation-job", args=[job.pk]))

    def test_data_annotator_can_open_unassigned_task_created_by_root(self):
        roles = ensure_platform_roles()
        self.other.groups.add(roles["DATA_ANNOTATOR"])
        client_project = ClientProject.objects.create(name="Root project", owner=self.owner)
        task = AnnotationTask.objects.create(name="Root task", client_project=client_project, created_by=self.owner)
        self.project.client_project = client_project
        self.project.annotation_task = task
        self.project.save(update_fields=["client_project", "annotation_task"])
        job = AnnotationJob.objects.create(task=task, video=self.project, stop_frame=99)
        self.client.force_login(self.other)
        task_list = self.client.get(reverse("annotation-task-list"))
        self.assertContains(task_list, task.name)
        self.assertEqual(self.client.get(reverse("annotation-task-detail", args=[task.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("annotation-job", args=[job.pk])).status_code, 200)

    def test_data_annotator_can_upload_operate_and_assign_annotation_task(self):
        roles = ensure_platform_roles()
        self.other.groups.add(roles["DATA_ANNOTATOR"])
        reviewer = get_user_model().objects.create_user("reviewer", password="test")
        reviewer.groups.add(roles["QA_QC_ENGINEER"])
        client_project = ClientProject.objects.create(name="Shared", owner=self.owner)
        self.project.client_project = client_project
        self.project.save(update_fields=["client_project"])
        self.client.force_login(self.other)

        response = self.client.post(reverse("annotation-task-create", args=[client_project.pk]), {
            "name": "Lobby day shift",
            "rules": [],
            "assignees": [self.other.pk],
            "reviewers": [reviewer.pk],
            "status": "ASSIGNED",
        })

        task = AnnotationTask.objects.get(name="Lobby day shift")
        self.assertRedirects(response, reverse("annotation-task-detail", args=[task.pk]))
        self.assertTrue(task.assignees.filter(pk=self.other.pk).exists())
        self.assertTrue(task.reviewers.filter(pk=reviewer.pk).exists())
        self.project.annotation_task = task
        self.project.save(update_fields=["annotation_task"])
        self.assertEqual(self.client.post(reverse("video-delete", args=[task.pk, self.project.pk])).status_code, 302)

    def test_data_annotator_can_edit_task_information_assignment_and_rules(self):
        roles = ensure_platform_roles()
        self.other.groups.add(roles["DATA_ANNOTATOR"])
        annotator = get_user_model().objects.create_user("annotator2", password="test")
        annotator.groups.add(roles["DATA_ANNOTATOR"])
        reviewer = get_user_model().objects.create_user("reviewer2", password="test")
        reviewer.groups.add(roles["QA_QC_ENGINEER"])
        client_project = ClientProject.objects.create(name="Editable", owner=self.owner)
        label = LabelClass.objects.create(client_project=client_project, name="person", label_type="rectangle")
        rule = Rule.objects.create(client_project=client_project, name="No phone")
        task = AnnotationTask.objects.create(name="Before", client_project=client_project, created_by=self.owner)
        self.client.force_login(self.other)
        page = self.client.get(reverse("annotation-task-edit", args=[task.pk]))
        self.assertContains(page, label.name)
        response = self.client.post(reverse("annotation-task-edit", args=[task.pk]), {
            "name": "After", "description": "Updated", "rules": [rule.pk],
            "assignees": [annotator.pk], "reviewers": [reviewer.pk], "status": "ASSIGNED",
        })
        task.refresh_from_db()
        self.assertRedirects(response, reverse("annotation-task-detail", args=[task.pk]))
        self.assertEqual((task.name, task.description, task.status), ("After", "Updated", "ASSIGNED"))
        self.assertEqual(list(task.rules.values_list("pk", flat=True)), [rule.pk])
        self.assertTrue(task.assignees.filter(pk=annotator.pk).exists())
        self.assertTrue(task.reviewers.filter(pk=reviewer.pk).exists())

    def test_data_annotator_can_delete_task_and_its_jobs(self):
        roles = ensure_platform_roles()
        self.other.groups.add(roles["DATA_ANNOTATOR"])
        client_project = ClientProject.objects.create(name="Delete task", owner=self.owner)
        task = AnnotationTask.objects.create(name="Disposable", client_project=client_project, created_by=self.owner)
        self.project.client_project = client_project
        self.project.annotation_task = task
        self.project.save(update_fields=["client_project", "annotation_task"])
        AnnotationJob.objects.create(task=task, video=self.project, stop_frame=0)
        self.client.force_login(self.other)
        response = self.client.post(reverse("annotation-task-delete", args=[task.pk]))
        self.assertRedirects(response, reverse("client-project-detail", args=[client_project.pk]))
        self.assertFalse(AnnotationTask.objects.filter(pk=task.pk).exists())
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())

    @patch("annotations.media.cv2.VideoCapture")
    @patch("annotations.media.probe", return_value={"width": 18, "height": 12, "fps": 25.0, "frame_count": 1})
    def test_data_annotator_can_create_task_with_uploaded_video_and_job(self, _probe, capture_class):
        import numpy as np
        capture = capture_class.return_value
        capture.read.side_effect = [(True, np.zeros((12, 18, 3), dtype=np.uint8)), (False, None)]
        roles = ensure_platform_roles()
        self.other.groups.add(roles["DATA_ANNOTATOR"])
        client_project = ClientProject.objects.create(name="Furama", owner=self.owner)
        LabelClass.objects.create(client_project=client_project, name="person", label_type="rectangle")
        self.client.force_login(self.other)
        response = self.client.post(reverse("annotation-task-create", args=[client_project.pk]), {
            "name": "Lobby camera", "assignees": [self.other.pk], "status": "ASSIGNED",
            "data_files": SimpleUploadedFile("lobby.mp4", b"fake-video", content_type="video/mp4"),
        })
        task = AnnotationTask.objects.get(name="Lobby camera")
        self.assertRedirects(response, reverse("annotation-task-detail", args=[task.pk]))
        self.assertEqual(task.jobs.count(), 1)
        self.assertEqual(task.jobs.get().video.classes.get().name, "person")
        self.assertEqual(task.jobs.get().video.media_kind, "IMAGE_SEQUENCE")
        self.assertEqual(task.jobs.get().video.frame_count, 1)

    def _jpeg(self, name, color):
        import numpy as np
        import cv2
        image = np.full((12, 18, 3), color, dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)
        return SimpleUploadedFile(name, encoded.tobytes(), content_type="image/jpeg")

    def test_folder_style_multiple_images_become_one_image_sequence_job(self):
        roles = ensure_platform_roles()
        self.other.groups.add(roles["DATA_ANNOTATOR"])
        client_project = ClientProject.objects.create(name="Images", owner=self.owner)
        self.client.force_login(self.other)
        response = self.client.post(reverse("annotation-task-create", args=[client_project.pk]), {
            "name": "Lobby images", "status": "DRAFT",
            "data_files": [self._jpeg("frame10.jpg", 10), self._jpeg("frame2.jpg", 20)],
        })
        task = AnnotationTask.objects.get(name="Lobby images")
        self.assertRedirects(response, reverse("annotation-task-detail", args=[task.pk]))
        media = task.jobs.get().video
        self.assertEqual(media.media_kind, "IMAGE_SEQUENCE")
        self.assertEqual(media.frame_count, 2)
        self.assertEqual(len(media.frame_manifest), 2)
        self.assertEqual(self.client.get(reverse("frame-image", args=[media.pk, 0])).status_code, 200)

    def test_zip_images_becomes_image_sequence_and_rejects_path_traversal(self):
        roles = ensure_platform_roles()
        self.other.groups.add(roles["DATA_ANNOTATOR"])
        client_project = ClientProject.objects.create(name="Archive", owner=self.owner)
        self.client.force_login(self.other)
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("frames/2.jpg", self._jpeg("2.jpg", 20).read())
            archive.writestr("frames/10.jpg", self._jpeg("10.jpg", 10).read())
        response = self.client.post(reverse("annotation-task-create", args=[client_project.pk]), {
            "name": "ZIP images", "status": "DRAFT",
            "data_files": SimpleUploadedFile("frames.zip", payload.getvalue(), content_type="application/zip"),
        })
        task = AnnotationTask.objects.get(name="ZIP images")
        self.assertRedirects(response, reverse("annotation-task-detail", args=[task.pk]))
        self.assertEqual(task.jobs.get().video.frame_count, 2)

        bad = io.BytesIO()
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("../escape.jpg", self._jpeg("escape.jpg", 1).read())
        response = self.client.post(reverse("annotation-task-create", args=[client_project.pk]), {
            "name": "Unsafe ZIP", "status": "DRAFT",
            "data_files": SimpleUploadedFile("unsafe.zip", bad.getvalue(), content_type="application/zip"),
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "đường dẫn không an toàn")
        self.assertFalse(AnnotationTask.objects.filter(name="Unsafe ZIP").exists())

    def test_assigned_annotator_can_open_job_and_save_project_schema_shape(self):
        roles = ensure_platform_roles()
        self.other.groups.add(roles["DATA_ANNOTATOR"])
        client_project = ClientProject.objects.create(name="Furama", owner=self.owner)
        label = LabelClass.objects.create(client_project=client_project, name="person", label_type="rectangle")
        task = AnnotationTask.objects.create(name="Lobby", client_project=client_project, created_by=self.other)
        task.assignees.add(self.other)
        self.project.client_project = client_project
        self.project.annotation_task = task
        self.project.save(update_fields=["client_project", "annotation_task"])
        job = AnnotationJob.objects.create(task=task, video=self.project, assignee=self.other, stop_frame=99)
        self.client.force_login(self.other)
        page = self.client.get(reverse("annotation-job", args=[job.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "nav.app-header{display:none}")
        self.assertContains(page, "function fitCanvas(resetZoom=false)")
        self.assertContains(page, "new ResizeObserver(()=>fitCanvas())")
        self.assertContains(page, "function beginSelect(x,y)")
        self.assertContains(page, "function deleteSelected()")
        self.assertContains(page, "current.label_id=next")
        self.assertContains(page, "function rectHandles(s)")
        self.assertContains(page, "function drawTag(")
        self.assertContains(page, "function undo()")
        response = self.client.post(
            reverse("save-job-frame", args=[job.pk, 3]),
            data=json.dumps({"shapes": [{"label_id": label.pk, "type": "rectangle", "points": [1, 2, 30, 40], "attributes": {}}]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AnnotationShape.objects.filter(job=job, frame_index=3, label=label).exists())

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

    def test_task_can_use_multiple_project_rules(self):
        client_project = ClientProject.objects.create(name="Customer A", owner=self.owner)
        self.project.client_project = client_project
        self.project.save(update_fields=["client_project"])
        first = Rule.objects.create(client_project=client_project, name="No phone")
        second = Rule.objects.create(client_project=client_project, name="Staff uniform")
        task = AnnotationTask.objects.create(name="Label lobby", client_project=client_project, created_by=self.owner)
        task.rules.add(first, second)
        self.assertEqual(task.rules.count(), 2)

    def test_customer_project_exposes_root_label_management(self):
        client_project = ClientProject.objects.create(name="Customer MQ", owner=self.owner)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("client-project-detail", args=[client_project.pk]))
        self.assertContains(response, "Tạo project label")

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

    def test_auto_annotation_maps_dynamic_detection_label_into_job_shapes(self):
        from .auto_annotation import convert_and_create, default_mapping, validate_mapping
        client_project = ClientProject.objects.create(name="Auto", owner=self.owner)
        label = LabelClass.objects.create(client_project=client_project, name="person", label_type="rectangle")
        task = AnnotationTask.objects.create(name="Auto task", client_project=client_project, created_by=self.owner)
        self.project.client_project = client_project
        self.project.annotation_task = task
        self.project.save(update_fields=["client_project", "annotation_task"])
        job = AnnotationJob.objects.create(task=task, video=self.project, stop_frame=0)
        function = AutoAnnotationFunction.objects.create(
            name="YOLO Detection", key="yolo-detection", endpoint_url="http://model:8080",
            kind="detector", spec=[{"name": "person", "type": "rectangle"}],
        )
        mapping = validate_mapping(function, client_project, default_mapping(function, client_project))
        run = AutoAnnotationRun.objects.create(task=task, function=function, mapping=mapping, requested_by=self.owner)
        created = convert_and_create(run, job, 0, [{
            "label": "person", "type": "rectangle", "points": [1, 2, 30, 40], "confidence": "0.91",
        }])
        self.assertEqual(len(created), 1)
        shape = AnnotationShape.objects.get()
        self.assertEqual((shape.label, shape.source, shape.points), (label, "auto", [1.0, 2.0, 30.0, 40.0]))

    def test_auto_annotation_page_exposes_visual_model_to_project_mapping(self):
        client_project = ClientProject.objects.create(name="Visual mapping", owner=self.owner)
        LabelClass.objects.create(client_project=client_project, name="person", label_type="rectangle", color="#00c900")
        task = AnnotationTask.objects.create(name="Mapping task", client_project=client_project, created_by=self.owner)
        AutoAnnotationFunction.objects.create(
            name="YOLO Detection", key="visual-yolo", endpoint_url="http://model:8080",
            kind="detector", spec=[{"name": "person", "type": "rectangle"}, {"name": "phone", "type": "rectangle"}],
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("annotation-task-detail", args=[task.pk]))
        self.assertContains(response, "Model class")
        self.assertContains(response, "Project label")
        self.assertContains(response, 'class="project-label"')
        self.assertContains(response, 'class="model-label"')
        self.assertContains(response, "eligible=labels.filter")
        self.assertContains(response, 'id="mappingRows"')
        self.assertContains(response, 'id="mappingPayload"')
        self.assertNotContains(response, "Label mapping nâng cao")

    @patch("annotations.tasks.run_auto_annotation.delay")
    def test_assigned_annotator_can_queue_task_auto_annotation(self, delay):
        roles = ensure_platform_roles()
        self.other.groups.add(roles["DATA_ANNOTATOR"])
        client_project = ClientProject.objects.create(name="Auto", owner=self.owner)
        LabelClass.objects.create(client_project=client_project, name="person", label_type="rectangle")
        task = AnnotationTask.objects.create(name="Auto task", client_project=client_project, created_by=self.other)
        task.assignees.add(self.other)
        self.project.client_project = client_project
        self.project.annotation_task = task
        self.project.frame_count = 1
        self.project.save(update_fields=["client_project", "annotation_task", "frame_count"])
        AnnotationJob.objects.create(task=task, video=self.project, stop_frame=0)
        function = AutoAnnotationFunction.objects.create(
            name="YOLO Detection", key="yolo-detection", endpoint_url="http://model:8080",
            kind="detector", spec=[{"name": "person", "type": "rectangle"}],
        )
        delay.return_value.id = "celery-1"
        self.client.force_login(self.other)
        response = self.client.post(reverse("start-auto-annotation", args=[task.pk]), {
            "function": function.pk, "threshold": "0.35",
        })
        self.assertRedirects(response, reverse("annotation-task-detail", args=[task.pk]))
        run = AutoAnnotationRun.objects.get()
        self.assertEqual((run.status, run.progress_total, run.mapping["person"]["name"]), ("QUEUED", 1, "person"))
