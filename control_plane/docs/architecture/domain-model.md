# Domain model

**Status:** Core implemented.

## Annotation domain

- `ClientProject`: customer workspace, chứa rules và video assets.
- `Rule`: logic nghiệp vụ thuộc một customer project; quan hệ many-to-many với
  video để một video có thể dùng cho nhiều rule.
- `Project`: tên model legacy của một video annotation asset; chứa video RAW,
  owner, metadata, coverage và liên kết tới `ClientProject`.
- `LabelClass`: nhãn GT, prompt, confidence và trạng thái enable.
- `BoxAnnotation`: bbox theo frame, source và review status.

Xem chi tiết quan hệ và chiến lược tương thích dữ liệu cũ tại
[Project, Rule và Video domain](../project-rule-video-domain.md).

## Quality domain

- `GroundTruthRelease`: snapshot version hóa, bất biến về mặt nghiệp vụ.
- `GroundTruthItem`: annotation đã copy vào release.
- `InferenceModel`: model/adapter có thể dùng toàn hệ thống.
- `Target`: endpoint cụ thể của một project, như Triton hoặc Kafka.
- `TestCase`: cấu hình và assertion có version.
- `TestRun`: snapshot input, correlation ID, state, metric và kết quả assertion.
- `EvaluationDataset`: dataset upload cho Model Quality, thuộc một `ClientProject`
  và độc lập với `Rule`.
- `EvaluationModel`: weight cùng metadata class và mapping của dataset evaluation.
- `ModelEvaluationRun`: inference/metrics snapshot của dataset và model.

Test run không đọc “latest GT” ngầm; nó lưu ID/version GT trong input snapshot để
kết quả có thể truy vết.
