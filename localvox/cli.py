import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="LocalVox CPU transcription server")
    parser.add_argument("command", choices=["serve", "download-model"], nargs="?", default="serve")
    args = parser.parse_args()
    if args.command == "download-model":
        from .models import download
        path = download(Path(os.environ.get("LOCALVOX_MODEL_DIR", ".cache/models")))
        print(f"Parakeet Ultra downloaded and SHA-256 verified: {path.name}")
    else:
        import uvicorn
        uvicorn.run("localvox.app:create_app", factory=True, host="0.0.0.0",
                    port=int(os.environ.get("LOCALVOX_PORT", "8000")), workers=1,
                    access_log=False, timeout_graceful_shutdown=30)


if __name__ == "__main__":
    main()
