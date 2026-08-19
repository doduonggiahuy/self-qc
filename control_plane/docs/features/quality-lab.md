# Quality Lab

**Status:** First vertical slice implemented.

Quality Lab nằm tại `/projects/<id>/quality/`.

Evaluator đầu tiên là `GT_VALIDATION`. Nó đếm annotation, frame đã annotate và
phân bố label, sau đó áp dụng assertion như:

```json
{"metric": "annotation_count", "operator": ">=", "value": 10}
```

Các loại detection, classification, pose và rule đã có trong domain nhưng chưa có
runner/evaluator nên phải được xem là planned. Execution hiện đồng bộ; service
`execute_run()` là boundary sẽ được gọi từ worker về sau.

