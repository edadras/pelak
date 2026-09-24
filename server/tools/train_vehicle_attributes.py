"""Train the optional fine-grained vehicle classifier (type + loaded/empty).

Dataset layout (Ultralytics classification format):

    dataset/
      train/
        sedan/  suv/  taxi/  van/  pickup_empty/  pickup_loaded/  light_truck_empty/  light_truck_loaded/
        truck_empty/  truck_loaded/  trailer_empty/  trailer_loaded/  minibus/  bus/  motorcycle/
      val/
        (same folders)

Collect crops from your own cameras with ``tools/export_crops.py``, sort them into the folders
(a few hundred images per class is a good start), then:

    python tools/train_vehicle_attributes.py --data dataset --epochs 40
    cp runs/classify/train/weights/best.pt ../model/vehicle_attr.pt

Workers load ``ATTR_MODEL`` (default ``model/vehicle_attr.pt``) automatically on restart.
"""
import argparse

from ultralytics import YOLO

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--model", default="yolov8s-cls.pt")
    ap.add_argument("--imgsz", type=int, default=224)
    ap.add_argument("--device", default="")
    a = ap.parse_args()
    YOLO(a.model).train(data=a.data, epochs=a.epochs, imgsz=a.imgsz, device=a.device or None)
