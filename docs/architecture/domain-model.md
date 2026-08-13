# Domain model

**Status:** Core implemented.

## Annotation domain

- `Project`: video RAW, owner, metadata và coverage.
- `LabelClass`: nhãn GT, prompt, confidence và trạng thái enable.
- `BoxAnnotation`: bbox theo frame, source và review status.

## Quality domain

- `GroundTruthRelease`: snapshot version hóa, bất biến về mặt nghiệp vụ.
- `GroundTruthItem`: annotation đã copy vào release.
- `InferenceModel`: model/adapter có thể dùng toàn hệ thống.
- `Target`: endpoint cụ thể của một project, như Triton hoặc Kafka.
- `TestCase`: cấu hình và assertion có version.
- `TestRun`: snapshot input, correlation ID, state, metric và kết quả assertion.

Test run không đọc “latest GT” ngầm; nó lưu ID/version GT trong input snapshot để
kết quả có thể truy vết.

