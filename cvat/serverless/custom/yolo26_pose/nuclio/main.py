import base64
import io
import json

from PIL import Image
from ultralytics import YOLO


COCO17 = {
    "nose": 0,
    "left_eye": 1,
    "right_eye": 2,
    "left_ear": 3,
    "right_ear": 4,
    "left_shoulder": 5,
    "right_shoulder": 6,
    "left_elbow": 7,
    "right_elbow": 8,
    "left_wrist": 9,
    "right_wrist": 10,
    "left_hip": 11,
    "right_hip": 12,
    "left_knee": 13,
    "right_knee": 14,
    "left_ankle": 15,
    "right_ankle": 16,
}


CVAT_KEYPOINTS = [
    "nose",
    "right_eye",
    "left_eye",
    "right_ear",
    "left_ear",
    "right_shoulder",
    "left_shoulder",
    "right_elbow",
    "left_elbow",
    "right_wrist",
    "left_wrist",
]


def init_context(context):
    context.logger.info("Loading YOLO26s pose model")

    model_path = "/opt/nuclio/yolo26s-pose.pt"

    context.user_data.model = YOLO(model_path)

    context.logger.info("YOLO26s pose model loaded successfully")


def handler(context, event):
    try:
        body = event.body

        if isinstance(body, bytes):
            body = body.decode("utf-8")

        if isinstance(body, str):
            body = json.loads(body)

        if not body or "image" not in body:
            return context.Response(
                body=json.dumps({
                    "error": "Missing 'image' field"
                }),
                headers={},
                content_type="application/json",
                status_code=400,
            )

        threshold = float(body.get("threshold", 0.25))

        image_bytes = base64.b64decode(body["image"])

        image = Image.open(
            io.BytesIO(image_bytes)
        ).convert("RGB")

        model = context.user_data.model

        results = model.predict(
            source=image,
            conf=threshold,
            verbose=False,
            device="cpu",
        )

        result = results[0]

        detections = []

        if result.keypoints is None:
            return context.Response(
                body=json.dumps([]),
                headers={},
                content_type="application/json",
                status_code=200,
            )

        keypoints_data = result.keypoints.data.cpu().tolist()

        if result.boxes is not None:
            box_confidences = result.boxes.conf.cpu().tolist()
        else:
            box_confidences = [1.0] * len(keypoints_data)

        for person_index, person_keypoints in enumerate(keypoints_data):

            person_confidence = float(
                box_confidences[person_index]
            )

            if person_confidence < threshold:
                continue

            elements = []

            for name in CVAT_KEYPOINTS:

                coco_index = COCO17[name]

                kp = person_keypoints[coco_index]

                x = float(kp[0])
                y = float(kp[1])

                kp_confidence = (
                    float(kp[2])
                    if len(kp) > 2
                    else 1.0
                )

                elements.append({
                    "label": name,
                    "type": "points",
                    "points": [
                        x,
                        y
                    ],
                    "outside": 0 if kp_confidence >= threshold else 1,
                    "confidence": str(kp_confidence),
                })

            detections.append({
                "label": "person_pose",
                "type": "skeleton",
                "confidence": str(person_confidence),
                "elements": elements,
            })

        return context.Response(
            body=json.dumps(detections),
            headers={},
            content_type="application/json",
            status_code=200,
        )

    except Exception as exc:
        context.logger.error(
            f"Pose inference failed: {exc}"
        )

        return context.Response(
            body=json.dumps({
                "error": str(exc)
            }),
            headers={},
            content_type="application/json",
            status_code=500,
        )