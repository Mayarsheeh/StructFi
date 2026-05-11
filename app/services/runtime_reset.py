from pathlib import Path
import shutil


class RuntimeResetService:
    def __init__(self):
        self.rendered_dir = Path("data/rendered")
        self.parsed_dir = Path("data/parsed")
        self.runtime_dir = Path("data/runtime")
        self.meta_dir = Path("data/meta")

        self.keep_dirs = [
            self.rendered_dir,
            self.parsed_dir,
            self.runtime_dir,
            self.meta_dir,
        ]

        for d in self.keep_dirs:
            d.mkdir(parents=True, exist_ok=True)

    def reset_all_runtime_state(self):
        self._clear_directory(self.rendered_dir)
        self._clear_directory(self.parsed_dir)
        self._clear_directory(self.runtime_dir)
        self._clear_directory(self.meta_dir)

    def reset_derived_state_for_new_upload(self):
        self._clear_directory(self.rendered_dir)
        self._clear_directory(self.parsed_dir)
        self._clear_directory(self.runtime_dir)
        self._clear_directory(self.meta_dir)

    def _clear_directory(self, directory: Path):
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            return

        for item in directory.iterdir():
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink(missing_ok=True)
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
            except Exception:
                pass