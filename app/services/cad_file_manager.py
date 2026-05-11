from pathlib import Path
from datetime import datetime
import subprocess
import shutil
import json
import os

import ezdxf


class CADFileManager:
    def __init__(self):
        self.upload_dir = Path("data/uploads")
        self.meta_dir = Path("data/meta")
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.latest_meta_path = self.meta_dir / "latest_cad.json"

    def save_cad_file(self, file_bytes: bytes, original_filename: str):
        ext = Path(original_filename).suffix.lower()

        if ext not in [".dxf", ".dwg"]:
            raise ValueError("Only DXF and DWG files are supported")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        source_name = f"cad_source_{timestamp}{ext}"
        source_path = self.upload_dir / source_name

        with open(source_path, "wb") as f:
            f.write(file_bytes)

        if ext == ".dxf":
            working_dxf_path = source_path
            conversion_info = {
                "converted": False,
                "source_format": "DXF",
                "working_format": "DXF"
            }
        else:
            working_dxf_path = self._convert_dwg_to_dxf(source_path)
            conversion_info = {
                "converted": True,
                "source_format": "DWG",
                "working_format": "DXF"
            }

        summary = self._parse_dxf_summary(working_dxf_path)

        metadata = {
            "source_file_name": source_name,
            "source_file_path": str(source_path).replace("\\", "/"),
            "working_dxf_file_name": working_dxf_path.name,
            "working_dxf_file_path": str(working_dxf_path).replace("\\", "/"),
            **conversion_info,
            "summary": summary
        }

        self.latest_meta_path.write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8"
        )
        return metadata

    def get_latest_cad(self):
        if not self.latest_meta_path.exists():
            return None

        try:
            return json.loads(self.latest_meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _parse_dxf_summary(self, dxf_path: Path):
        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()

        counts = {
            "LINE": 0,
            "LWPOLYLINE": 0,
            "POLYLINE": 0,
            "TEXT": 0,
            "MTEXT": 0,
            "CIRCLE": 0,
            "ARC": 0,
            "OTHER": 0
        }

        total = 0
        for entity in msp:
            total += 1
            dxftype = entity.dxftype()
            if dxftype in counts:
                counts[dxftype] += 1
            else:
                counts["OTHER"] += 1

        return {
            "total_entities": total,
            "entity_counts": counts
        }

    def _convert_dwg_to_dxf(self, dwg_path: Path) -> Path:
        converter = self._find_oda_converter()
        if converter is None:
            raise ValueError(
                "DWG upload detected, but ODA File Converter was not found. "
                "Install ODA File Converter or upload DXF instead."
            )

        out_dir = self.upload_dir / "converted"
        out_dir.mkdir(parents=True, exist_ok=True)

        temp_input_dir = self.upload_dir / "dwg_input"
        temp_input_dir.mkdir(parents=True, exist_ok=True)

        working_input = temp_input_dir / dwg_path.name
        shutil.copy2(dwg_path, working_input)

        cmd = [
            str(converter),
            str(temp_input_dir),
            str(out_dir),
            "ACAD2018",
            "DXF",
            "0",
            "1"
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            shell=False
        )

        converted_path = out_dir / f"{dwg_path.stem}.dxf"

        if result.returncode != 0:
            raise ValueError(
                f"DWG to DXF conversion failed. Converter output: {result.stderr or result.stdout}"
            )

        if not converted_path.exists():
            raise ValueError(
                "DWG to DXF conversion finished but no DXF file was produced."
            )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_dxf = self.upload_dir / f"cad_converted_{timestamp}.dxf"
        shutil.copy2(converted_path, final_dxf)

        return final_dxf

    def _find_oda_converter(self):
        env_path = os.environ.get("ODA_FILE_CONVERTER")
        if env_path and Path(env_path).exists():
            return Path(env_path)

        candidates = [
            Path("C:/Program Files/ODA/ODAFileConverter/ODAFileConverter.exe"),
            Path("C:/Program Files/ODA/ODAFileConverter 25.12.0/ODAFileConverter.exe"),
            Path("C:/Program Files/ODA/ODAFileConverter 25.9.0/ODAFileConverter.exe"),
            Path("C:/Program Files/ODA/ODAFileConverter 24.12.0/ODAFileConverter.exe"),
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None