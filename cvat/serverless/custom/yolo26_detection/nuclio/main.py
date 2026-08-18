import base64
import io
import json

from PIL import Image
from ultralytics import YOLO


def init_context(context):
    context.logger.info("Loading YOLO26s detection model")

    model_path = "/opt/nuclio/yolo26s.pt"

    model = YOLO(model_path)

    context.user_data.model = model

    context.logger.info("YOLO26s detection model loaded successfully")


def handler(context, event):
    try:
        body = event.body

        if isinstance(body, bytes):
            body = body.decode("utf-8")

        if isinstance(body, str):
            body = json.loads(body)

        image_b64 = body["image"]

        image_bytes = base64.b64decode(image_b64)

        image = Image.open(
            io.BytesIO(image_bytes)
        ).convert("RGB")

        model = context.user_data.model

        results = model.predict(
            source=image,
            conf=0.25,
            verbose=False,
            device="cpu",
        )

        result = results[0]

        detections = []

        if result.boxes is not None:
            for box in result.boxes:
                class_id = int(box.cls.item())

                # COCO:
                # 0  = person
                # 67 = cell phone
                if class_id not in (0, 67):
                    continue

                confidence = float(box.conf.item())

                x1, y1, x2, y2 = box.xyxy[0].tolist()

                label = result.names[class_id]

                detections.append(
                    {
                        "confidence": str(confidence),
                        "label": label,
                        "points": [
                            float(x1),
                            float(y1),
                            float(x2),
                            float(y2),
                        ],
                        "type": "rectangle",
                    }
                )

        return context.Response(
            body=json.dumps(detections),
            headers={},
            content_type="application/json",
            status_code=200,
        )

    except Exception as exc:
        context.logger.error(f"Inference failed: {exc}")

        return context.Response(
            body=json.dumps(
                {
                    "error": str(exc)
                }
            ),
            headers={},
            content_type="application/json",
            status_code=500,
        )
