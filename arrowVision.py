import threading
import cv2
from ultralytics import YOLO

stream_url = "MJPEG주소다_애송이"
weights = "arrow-model/model_release/arrowBest.pt"
conf=0.5

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