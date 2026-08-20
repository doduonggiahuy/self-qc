# Annotation capability audit: Freeflow vs CVAT

**Cập nhật:** 2026-08-20  
**Phạm vi:** annotation 2D ảnh/video cho workflow Freeflow; không lấy các tính
năng 3D, audio, cloud storage, organization, webhook của CVAT làm phạm vi MVP.

## Mục tiêu

Freeflow không cần clone toàn bộ CVAT. Nó phải có trải nghiệm tương đương CVAT ở
luồng được dùng: Project schema -> Task/data -> Job -> annotate/review -> export
Ground Truth, cùng Automatic Annotation theo model-function contract.

## Ma trận capability

| Nhóm | CVAT | Freeflow hiện tại | Gap / quyết định |
| --- | --- | --- | --- |
| Project | Tạo/sửa/xóa, assignee, description, labels Raw/Constructor, advanced config | Tạo project, description, Raw/Constructor, label màu, skeleton, rule; edit project metadata chưa rõ ràng | **P1:** Project actions/menu chuẩn; edit metadata; không dùng dropdown native cho hành động phá hủy |
| Label schema | Rectangle, polygon, polyline, points, ellipse, cuboid, mask, tag, skeleton; attributes; màu; edit/delete/reorder | Rectangle, skeleton, tag trong schema; canvas mới dùng rectangle/skeleton; attribute cơ bản; edit/delete label | **P0:** hoàn thiện label editor/reorder/validation; **P2:** polygon/polyline/points/mask/ellipse. Cuboid/3D out of scope |
| Skeleton schema | GUI node/edge editor, sublabel attribute, raw CVAT round-trip | Import/export Raw CVAT cơ bản; point color/name/x/y và edge text | **P0:** visual node-edge editor và validation edge; không chỉ nhập chuỗi `a-b` |
| Task | Tạo/sửa/xóa, Project inheritance, subset, advanced/quality config, labels fallback, jobs | Tạo/sửa/xóa, inherit labels, data upload, assignee/reviewer/rules/status | **P0:** subset, task owner/assignee UX, per-job assignment; **P1:** advanced configuration đúng nhu cầu (chunk/segment/frame step), quality config |
| Data ingest | Images, archive, video, remote/cloud; progress, validate, server-side import | Images/folder, ZIP, video->frames, basic guard | **P0:** ingestion progress/error rõ; không re-encode frame lần hai khi inference. **P2:** cloud/remote source |
| Job management | Job segments/overlap, stage/state/assignee, create job, split/merge, progress | Một job cho mỗi source, stage/state fields, task-level assignee/reviewer | **P0:** hiển thị và sửa assignee/reviewer/stage/state theo job; **P1:** segment/overlap và split job |
| Canvas navigation | Frame seek, play, speed, frame step, filters, search, rotation, fit/zoom/pan | Slider, previous/next, wheel zoom neo chuột, fit, Hand/Space-drag pan | **P1:** frame input, playback, speed/frame step, rotation, search/filter |
| Canvas objects | Shapes, tracks, tags; object list, select, layer, copy/paste, lock/hide, grouping, propagation | Rectangle/skeleton; select/move/resize bbox; edit/delete point; card đổi label/lock/hide/focus/xóa; attributes; undo/redo | **P0:** copy/paste, duplicate and propagate. **P1:** tracks/interpolation. **P2:** group/merge/split/layer management |
| Drawing tools | Rectangle, polygon, polyline, points, ellipse, mask, skeleton, tag; draw/edit modes | Rectangle and skeleton only | **P0:** fix Select/Hand/Skeleton interaction. **P2:** add polygon, polyline, points, ellipse, mask; tag only when UI stores tag shapes |
| Review / QA | Job stage workflow, reviewer, issues/comments, conflicts, quality reports | Reviewer selector only; no issue/comment/review decision | **P1:** reviewer queue, accept/reject, comment/issue at frame/object. Quality reports will integrate with Quality service, not copied wholesale |
| Annotation state | Shape IDs persisted incrementally, client state, autosave/recovery, history | Save frame replaces all shapes; in-memory undo/redo only | **P0:** prevent accidental overwrite and add autosave/draft recovery. **P1:** per-shape update API and audit trail |
| Import/export | Many Datumaro/CVAT/COCO/YOLO formats, task backup, upload annotations | Legacy JSONL only, and it does not export new `AnnotationShape` data reliably | **P0:** export current AnnotationShape to CVAT JSON + COCO/YOLO as needed by Training. **P1:** import CVAT JSON/COCO/YOLO and backup/restore |
| Auto annotation | Model registry/function spec, mapper, run progress/cancel, action menu | Remote function spec, label/keypoint mapping, async run/progress/cancel | **P0:** raw frame bytes (no second JPEG encode), worker health/readiness, run retry/error diagnostics, batch inference. **P1:** run selected frames/job, preview before apply, merge policy |
| Permissions | Organization/project/task/job policy | Root creates Project/schema/rules; Data Annotator runs Task/Job | **P0:** current backend boundary is broadly correct; add project membership/team lead scope before scaling users |

## Evidence from source

- CVAT canvas controls: `cvat/cvat-ui/src/components/annotation-page/standard-workspace/controls-side-bar/`.
- CVAT object sidebar/actions: `cvat/cvat-ui/src/components/annotation-page/standard-workspace/objects-side-bar/`.
- CVAT project/task/label editors: `cvat/cvat-ui/src/components/create-project-page/`,
  `create-task-page/`, `labels-editor/`.
- Freeflow implementation: `annotations/models.py`, `annotations/views.py`,
  `annotations/auto_annotation.py`, and `control_plane/templates/annotations/`.

## P0 delivery order

1. Fix media fidelity and Auto Annotation execution reliability: direct original frame
   bytes, worker readiness, batch inference, run diagnostics.
2. Finish canvas base interaction: Hand/Space pan, object-state panel, copy/paste,
   duplicate/propagate, safer save/autosave.
3. Complete task/job operational controls: subset, job assignee/reviewer/stage/state,
   visible progress and upload progress.
4. Complete schema editor: visual skeleton configuration, label ordering and robust
   label edit/delete warnings.
5. Export the new annotation data model for Training/Quality; do not extend the
   legacy `BoxAnnotation` export path.

## Explicit non-goals until P0/P1 works

- Full CVAT 3D, audio, cuboids, cloud storage, organization/webhook/analytics;
- mask/polygon tracking before current rectangle/skeleton workflow is reliable;
- importing all Datumaro formats before the export contract is stable.
