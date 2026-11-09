from dataclasses import dataclass, field
from pathlib import Path
import os


def number(name: str, default: int) -> int:
    value = int(os.environ.get(name, default))
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class Settings:
    token: str = field(repr=False)
    backend: str = "parakeet"
    model_dir: Path = Path(".cache/models")
    temp_dir: Path = Path(".cache/tmp")
    max_files: int = 8
    max_file_bytes: int = 25 * 1024 * 1024
    max_seconds: int = 300
    max_pending: int = 2
    queue_timeout: int = 30
    upload_timeout: int = 120
    task_timeout: int = 180
    cpu_threads: int = 2
    secure_cookie: bool = False

    def __post_init__(self):
        if len(self.token) < 24 or self.token == "replace-with-a-long-random-token":
            raise ValueError("Set LOCALVOX_TOKEN to a random secret of at least 24 characters")
        if self.backend not in {"parakeet", "mock"}:
            raise ValueError("LOCALVOX_BACKEND must be parakeet or mock")
        for name in ("max_files", "max_file_bytes", "max_seconds", "max_pending",
                     "queue_timeout", "upload_timeout", "task_timeout", "cpu_threads"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")

    @property
    def max_body_bytes(self):
        return self.max_files * self.max_file_bytes + 65536

    @classmethod
    def from_env(cls):
        return cls(
            token=os.environ.get("LOCALVOX_TOKEN", ""),
            backend=os.environ.get("LOCALVOX_BACKEND", "parakeet"),
            model_dir=Path(os.environ.get("LOCALVOX_MODEL_DIR", ".cache/models")),
            temp_dir=Path(os.environ.get("LOCALVOX_TEMP_DIR", ".cache/tmp")),
            max_files=number("LOCALVOX_MAX_FILES", 8),
            max_file_bytes=number("LOCALVOX_MAX_FILE_MB", 25) * 1024 * 1024,
            max_seconds=number("LOCALVOX_MAX_SECONDS", 300),
            max_pending=number("LOCALVOX_MAX_PENDING", 2),
            queue_timeout=number("LOCALVOX_QUEUE_TIMEOUT", 30),
            upload_timeout=number("LOCALVOX_UPLOAD_TIMEOUT", 120),
            task_timeout=number("LOCALVOX_TASK_TIMEOUT", 180),
            cpu_threads=number("LOCALVOX_CPU_THREADS", 2),
            secure_cookie=os.environ.get("LOCALVOX_SECURE_COOKIE", "false").lower() == "true",
        )
