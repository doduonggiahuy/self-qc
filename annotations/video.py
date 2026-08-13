import cv2


def probe(path):
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            raise ValueError("Không thể mở video")
        return {
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": float(cap.get(cv2.CAP_PROP_FPS) or 0),
            "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        }
    finally:
        cap.release()


def read_frame(path, frame_index):
    cap = cv2.VideoCapture(path)
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
        ok, frame = cap.read()
        if not ok:
            raise ValueError(f"Không đọc được frame {frame_index}")
        return frame
    finally:
        cap.release()

