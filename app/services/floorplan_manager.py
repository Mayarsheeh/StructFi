from pathlib import Path
from datetime import datetime
from PIL import Image


class FloorplanManager:
    def __init__(self):
        self.upload_dir = Path("data/uploads")
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def save_floorplan(self, file_bytes: bytes, original_filename: str):
        extension = Path(original_filename).suffix.lower()

        if extension not in [".png", ".jpg", ".jpeg"]:
            raise ValueError("Only PNG, JPG, and JPEG files are supported")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = f"floorplan_{timestamp}{extension}"
        file_path = self.upload_dir / safe_name

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        image = Image.open(file_path)
        width, height = image.size

        return {
            "file_name": safe_name,
            "file_path": str(file_path).replace("\\", "/"),
            "width": width,
            "height": height
        }

    def get_latest_floorplan(self):
        files = sorted(
            list(self.upload_dir.glob("*.png")) +
            list(self.upload_dir.glob("*.jpg")) +
            list(self.upload_dir.glob("*.jpeg")),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        if not files:
            return None

        latest = files[0]
        image = Image.open(latest)
        width, height = image.size

        return {
            "file_name": latest.name,
            "file_path": str(latest).replace("\\", "/"),
            "width": width,
            "height": height
        }