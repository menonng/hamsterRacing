import threading
import cv2
from ultralytics import YOLO

stream_url = "http://192.168.66.1:9527/videostream.cgi?loginuse=admin&loginpas=admin"
weights = "runs\detect/arrow_yolov8n-3/weights/best.pt"
conf=0.05

direction = None
lock = threading.Lock()


def _worker():
    global direction
    cap = cv2.VideoCapture(stream_url)
    model = YOLO(weights)

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        results = model.predict(frame, conf=conf, verbose=False)[0]
        label = None
        if len(results.boxes) > 0:
            best = max(results.boxes, key=lambda b: float(b.conf))
            name = model.names[int(best.cls)]
            if name in ("left", "right"):
                label = name

        with lock:
            direction = label

        cv2.imshow("arrow", results.plot())
        cv2.waitKey(1)


def start():
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def get_direction():
    with lock:
        return direction