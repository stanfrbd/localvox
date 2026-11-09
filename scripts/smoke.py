"""Start the real server, call health + multipart API, verify logs and cleanup."""
import argparse
import io
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import wave

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["mock", "parakeet"], default="mock")
    parser.add_argument("--audio", type=Path)
    args = parser.parse_args()
    if args.audio:
        audio = args.audio.read_bytes()
    else:
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(b"\0\0" * 1600)
        audio = output.getvalue()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
    token = secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory(prefix="localvox-smoke-") as directory:
        env = {**os.environ, "LOCALVOX_TOKEN": token, "LOCALVOX_BACKEND": args.backend,
               "LOCALVOX_PORT": str(port), "LOCALVOX_TEMP_DIR": directory + "/audio"}
        with tempfile.TemporaryFile() as log:
            process = subprocess.Popen([sys.executable, "-m", "localvox.cli", "serve"], env=env, stdout=log, stderr=log)
            try:
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=240) as client:
                    for attempt in range(100):
                        if process.poll() is not None:
                            raise RuntimeError("Server exited before startup")
                        try:
                            if client.get("/health").json() == {"status": "ok"}: break
                        except httpx.TransportError: pass
                        time.sleep(.1)
                    else: raise RuntimeError("Server startup timeout")
                    assert client.post("/api/transcribe").status_code == 401
                    started = time.monotonic()
                    response = client.post("/api/transcribe", headers={"Authorization": "Bearer " + token},
                                           files=[("files", ("sample.wav", audio, "audio/wav"))])
                    assert response.status_code == 200, response.text
                    result = response.json()["results"][0]
                    print(json.dumps({"backend": args.backend, "wall_seconds": round(time.monotonic()-started, 3), **result}, indent=2))
                    assert result["status"] == "done", result
                    assert token not in response.text
            finally:
                process.terminate()
                try: process.wait(timeout=35)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
                log.seek(0)
                logs = log.read().decode(errors="replace")
                assert token not in logs
                print("Server stopped; token absent from logs.")
            assert not list(Path(directory).rglob("file-*"))
            assert not list(Path(directory).rglob("localvox-*"))
            print("Temporary audio cleanup verified.")


if __name__ == "__main__":
    main()
