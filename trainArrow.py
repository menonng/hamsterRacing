from ultralytics import YOLO

model = YOLO("yolov8n.pt")

model.train(
    data="merged_arrow/data.yaml",
    epochs=100,
    imgsz=640,
    batch=16,
    patience=20,
    name="arrow_yolov8n",
)

metrics = model.val()
print(metrics.box.map50)
print(metrics.box.map)
