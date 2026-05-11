from pathlib import Path
from PIL import Image
import cv2
import numpy as np


class ImageRoomDetector:
    def __init__(self):
        self.upload_dir = Path("data/uploads")
        self.detected_dir = Path("data/detected")
        self.detected_dir.mkdir(parents=True, exist_ok=True)

    def detect_rooms_from_image(self, image_path: str):
        image_path = Path(image_path)
        if not image_path.exists():
            raise ValueError("Image file not found")

        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError("Failed to read image")

        original = image.copy()
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

        kernel = np.ones((3, 3), np.uint8)
        morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates = []
        annotated = original.copy()

        image_h, image_w = gray.shape
        min_area = max(1500, int((image_w * image_h) * 0.002))

        room_id = 1

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue

            x, y, w, h = cv2.boundingRect(contour)

            if w < 40 or h < 40:
                continue

            aspect_ratio = w / float(h)
            if aspect_ratio < 0.25 or aspect_ratio > 6:
                continue

            extent = area / float(w * h)
            if extent < 0.45:
                continue

            room = {
                "id": room_id,
                "name": f"Detected-Room-{room_id}",
                "x": int(x),
                "y": int(y),
                "width": int(w),
                "height": int(h),
                "zone": "staff"
            }
            candidates.append(room)

            cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(
                annotated,
                f"Room-{room_id}",
                (x + 5, y + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 0),
                2
            )

            room_id += 1

        annotated_name = f"{image_path.stem}_detected.png"
        annotated_path = self.detected_dir / annotated_name
        cv2.imwrite(str(annotated_path), annotated)

        return {
            "source_image": str(image_path).replace("\\", "/"),
            "annotated_image": str(annotated_path).replace("\\", "/"),
            "room_count": len(candidates),
            "rooms": candidates
        }

    def get_latest_detected_image(self):
        files = sorted(
            list(self.detected_dir.glob("*.png")),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        if not files:
            return None

        latest = files[0]
        img = Image.open(latest)
        width, height = img.size

        return {
            "file_name": latest.name,
            "file_path": str(latest).replace("\\", "/"),
            "width": width,
            "height": height
        }