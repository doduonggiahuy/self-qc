import os
import threading

import cv2
from PIL import Image


_LOCK = threading.Lock()
_CACHE = {}


def _model_inputs_on_device(inputs, model):
    """Move processor tensors without mixing float32 inputs with a fp16 GPU model."""
    import torch

    moved = {}
    for key, value in inputs.items():
        if torch.is_floating_point(value):
            moved[key] = value.to(device=model.device, dtype=model.dtype)
        else:
            moved[key] = value.to(device=model.device)
    return moved


def predict_with_model(image, label_classes, inference_model=None):
    if inference_model is None:
        reference = os.getenv("YOLO_WORLD_MODEL", "yolov8s-worldv2.pt")
        return YoloWorldAdapter(reference).predict(image, label_classes)
    adapters = {
        "quality.adapters.YoloWorldAdapter": YoloWorldAdapter,
        "quality.adapters.Florence2Adapter": Florence2Adapter,
        "quality.adapters.GroundingDinoAdapter": GroundingDinoAdapter,
    }
    adapter = adapters.get(inference_model.adapter)
    if adapter is None:
        raise ValueError(f"Adapter chưa được hỗ trợ: {inference_model.adapter}")
    return adapter(inference_model.runtime_reference, inference_model.default_config).predict(image, label_classes)


class YoloWorldAdapter:
    def __init__(self, reference, config=None):
        if not os.path.isabs(reference):
            models_dir = os.getenv("YOLO_MODELS_DIR", os.getenv("QC_MODEL_ROOT", "/app/models"))
            os.makedirs(models_dir, exist_ok=True)
            reference = os.path.join(models_dir, reference)
        self.reference = reference
        self.config = config or {}

    def predict(self, image, label_classes):
        from ultralytics import YOLOWorld
        prompts = [item.prompt.strip() or item.name for item in label_classes]
        if not prompts:
            return []
        with _LOCK:
            model = _CACHE.get(("yolo-world", self.reference))
            if model is None:
                model = _CACHE[("yolo-world", self.reference)] = YOLOWorld(self.reference)
            model.set_classes(prompts)
            results = model.predict(
                image, conf=min(item.confidence for item in label_classes),
                device=self.config.get("device", os.getenv("YOLO_DEVICE", "0")), verbose=False,
            )
        proposals = []
        for result in results:
            if result.boxes is None:
                continue
            for xyxy, cls_id, confidence in zip(result.boxes.xyxy.cpu().tolist(), result.boxes.cls.cpu().tolist(), result.boxes.conf.cpu().tolist()):
                index = int(cls_id)
                if 0 <= index < len(label_classes) and float(confidence) >= label_classes[index].confidence:
                    proposals.append(_proposal(label_classes[index], xyxy, confidence, prompts[index]))
        return proposals


class Florence2Adapter:
    def __init__(self, reference, config=None):
        self.reference = reference
        self.config = config or {}

    def _load(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor
        key = ("florence-2", self.reference)
        if key not in _CACHE:
            processor = AutoProcessor.from_pretrained(self.reference, trust_remote_code=True, local_files_only=True)
            model = AutoModelForCausalLM.from_pretrained(
                self.reference, trust_remote_code=True, local_files_only=True,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            ).to(self.config.get("device", "cuda" if torch.cuda.is_available() else "cpu")).eval()
            _CACHE[key] = (model, processor)
        return _CACHE[key]

    def predict(self, image, label_classes):
        import torch
        pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        proposals = []
        with _LOCK, torch.inference_mode():
            model, processor = self._load()
            for label_class in label_classes:
                prompt = label_class.prompt.strip() or label_class.name
                task = "<CAPTION_TO_PHRASE_GROUNDING>"
                inputs = processor(text=task + prompt, images=pil_image, return_tensors="pt")
                inputs = _model_inputs_on_device(inputs, model)
                generated = model.generate(**inputs, max_new_tokens=1024, num_beams=3, do_sample=False)
                text = processor.batch_decode(generated, skip_special_tokens=False)[0]
                parsed = processor.post_process_generation(text, task=task, image_size=pil_image.size).get(task, {})
                for bbox in parsed.get("bboxes", []):
                    proposals.append(_proposal(label_class, bbox, None, prompt))
        return proposals


class GroundingDinoAdapter:
    def __init__(self, reference, config=None):
        self.reference = reference
        self.config = config or {}

    def _load(self):
        import torch
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
        key = ("grounding-dino", self.reference)
        if key not in _CACHE:
            processor = AutoProcessor.from_pretrained(self.reference, local_files_only=True)
            # The Transformers Grounding DINO implementation creates internal
            # float32 tensors for text/vision fusion. Keeping this model fp32
            # avoids the Float/Half matmul mismatch seen with fp16 checkpoints.
            model = AutoModelForZeroShotObjectDetection.from_pretrained(
                self.reference, local_files_only=True, torch_dtype=torch.float32,
            ).to(self.config.get("device", "cuda" if torch.cuda.is_available() else "cpu")).eval()
            _CACHE[key] = (model, processor)
        return _CACHE[key]

    def predict(self, image, label_classes):
        import torch
        pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        prompts = [item.prompt.strip() or item.name for item in label_classes]
        with _LOCK, torch.inference_mode():
            model, processor = self._load()
            inputs = processor(images=pil_image, text=[prompts], return_tensors="pt")
            inputs = _model_inputs_on_device(inputs, model)
            outputs = model(**inputs)
            result = processor.post_process_grounded_object_detection(
                outputs, inputs["input_ids"],
                threshold=float(self.config.get("box_threshold", 0.15)),
                text_threshold=float(self.config.get("text_threshold", 0.15)),
                target_sizes=[pil_image.size[::-1]],
            )[0]
        proposals = []
        labels = result.get("text_labels", result.get("labels", []))
        for bbox, score, label in zip(result["boxes"].cpu().tolist(), result["scores"].cpu().tolist(), labels):
            index = _best_label_index(str(label), prompts)
            if index is not None and float(score) >= label_classes[index].confidence:
                proposals.append(_proposal(label_classes[index], bbox, score, prompts[index]))
        return proposals


def _best_label_index(label, prompts):
    normalized = label.lower().strip()
    for index, prompt in enumerate(prompts):
        if normalized in prompt.lower() or prompt.lower() in normalized:
            return index
    return None


def _proposal(label_class, bbox, confidence, prompt):
    return {"label_class": label_class, "bbox": [float(value) for value in bbox], "confidence": None if confidence is None else float(confidence), "prompt": prompt}
