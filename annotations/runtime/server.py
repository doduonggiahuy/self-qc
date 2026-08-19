"""Small HTTP execution service for YOLO automatic annotation functions."""

import base64
import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image
from ultralytics import YOLO


MODEL_PATH = os.environ["AUTO_MODEL_PATH"]
MODEL_KIND = os.environ.get("AUTO_MODEL_KIND", "detector")
MODEL_DEVICE = os.environ.get("AUTO_MODEL_DEVICE", "cpu")
POSE_LABEL = os.environ.get("AUTO_POSE_LABEL", "person_pose")
POSE_KEYPOINTS = json.loads(os.environ.get("AUTO_POSE_KEYPOINTS", "[]"))
PORT = int(os.environ.get("AUTO_MODEL_PORT", "8080"))

model = YOLO(MODEL_PATH)
model_lock = threading.Lock()


def function_spec():
    if MODEL_KIND == "pose":
        return [{
            "name": POSE_LABEL,
            "type": "skeleton",
            "sublabels": [{"id": index, "name": name, "type": "points"} for index, name in enumerate(POSE_KEYPOINTS)],
        }]
    return [{"id": int(class_id), "name": name, "type": "rectangle"} for class_id, name in model.names.items()]


def predict(body):
    image = Image.open(io.BytesIO(base64.b64decode(body["image"]))).convert("RGB")
    threshold = float(body.get("threshold", 0.25))
    with model_lock:
        result = model.predict(source=image, conf=threshold, verbose=False, device=MODEL_DEVICE)[0]
    if MODEL_KIND == "pose":
        output = []
        if result.keypoints is None:
            return output
        keypoints = result.keypoints.data.cpu().tolist()
        confidences = result.boxes.conf.cpu().tolist() if result.boxes is not None else [1.0] * len(keypoints)
        for person_points, confidence in zip(keypoints, confidences):
            elements = []
            for index, name in enumerate(POSE_KEYPOINTS):
                if index >= len(person_points):
                    break
                point = person_points[index]
                point_confidence = float(point[2]) if len(point) > 2 else 1.0
                elements.append({
                    "label": name, "type": "points",
                    "points": [float(point[0]), float(point[1])],
                    "outside": int(point_confidence < threshold),
                    "confidence": point_confidence,
                })
            output.append({"label": POSE_LABEL, "type": "skeleton", "confidence": float(confidence), "elements": elements})
        return output
    output = []
    if result.boxes is not None:
        for box in result.boxes:
            class_id = int(box.cls.item())
            output.append({
                "label": result.names[class_id], "type": "rectangle",
                "points": [float(value) for value in box.xyxy[0].tolist()],
                "confidence": float(box.conf.item()),
            })
    return output


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ready", "kind": MODEL_KIND, "device": MODEL_DEVICE})
        elif self.path == "/spec":
            self.send_json(200, function_spec())
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path not in {"/", "/infer"}:
            self.send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 64 * 1024 * 1024:
                raise ValueError("invalid request size")
            body = json.loads(self.rfile.read(length))
            if "image" not in body:
                raise ValueError("missing image")
            self.send_json(200, predict(body))
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}", flush=True)


if __name__ == "__main__":
    print(json.dumps({"event": "model_ready", "path": MODEL_PATH, "kind": MODEL_KIND, "device": MODEL_DEVICE, "labels": len(function_spec())}), flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
