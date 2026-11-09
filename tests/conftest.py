import io
import wave
import pytest
from fastapi.testclient import TestClient
from localvox.app import create_app
from localvox.config import Settings

TOKEN = "test-only-random-token-12345678901234567890"


def wav_bytes(seconds=0.1):
    out = io.BytesIO()
    with wave.open(out, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0\0" * int(16000 * seconds))
    return out.getvalue()


@pytest.fixture
def audio():
    return wav_bytes()


@pytest.fixture
def settings(tmp_path):
    return Settings(token=TOKEN, backend="mock", model_dir=tmp_path / "models", temp_dir=tmp_path / "temp",
                    max_file_bytes=8192, max_seconds=1, max_files=3)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {TOKEN}"}
