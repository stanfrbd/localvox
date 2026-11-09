"""Explicit, pinned model provisioning; never downloads during inference."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request
import fcntl

CATALOG = json.loads(Path(__file__).with_name("catalog.json").read_text())


def verified(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size != CATALOG["size"]:
        return False
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest() == CATALOG["sha256"]


def download(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / CATALOG["filename"]
    # Serialize downloaders on Linux. Never replace an mmap'ed file in place.
    with (directory / ".download.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if verified(target):
            return target
        url = (f'https://huggingface.co/{CATALOG["repository"]}/resolve/'
               f'{CATALOG["revision"]}/{CATALOG["filename"]}')
        try:
            with tempfile.NamedTemporaryFile(dir=directory, suffix=".part", delete=False) as out:
                partial = Path(out.name)
                with urllib.request.urlopen(url, timeout=60) as response:
                    total = 0
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > CATALOG["size"]:
                            raise RuntimeError("Download exceeded catalog size")
                        out.write(chunk)
            if not verified(partial):
                raise RuntimeError("Model size or SHA-256 mismatch")
            os.replace(partial, target)
        finally:
            if "partial" in locals():
                partial.unlink(missing_ok=True)
    return target
