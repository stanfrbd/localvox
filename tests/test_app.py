from dataclasses import replace
import json
from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient
import pytest

from localvox.app import create_app
from localvox.engine import MockEngine
from localvox.config import Settings
from conftest import TOKEN, wav_bytes


def upload(client, auth, audio, name="voice.wav", route="/api/transcribe"):
    return client.post(route, headers=auth, files=[("files", (name, audio, "audio/wav"))])


def test_health_is_minimal(client):
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("route", ["/api/transcribe", "/share", "/api/model", "/app.js", "/style.css", "/openapi.json"])
def test_private_without_token(client, route):
    response = client.post(route) if route in {"/api/transcribe", "/share"} else client.get(route)
    assert response.status_code == 401


def test_bad_token_and_home_redirect(client, audio):
    assert upload(client, {"Authorization": "Bearer wrong"}, audio).status_code == 401
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"


def test_valid_audio(client, auth, audio, settings):
    response = upload(client, auth, audio)
    assert response.status_code == 200
    row = response.json()["results"][0]
    assert row["status"] == "done"
    assert row["text"].startswith("[MOCK]")
    assert row["duration_seconds"] == pytest.approx(.1)
    assert not list(settings.temp_dir.rglob("input"))
    assert not list(settings.temp_dir.rglob("audio.f32"))


def test_mixed_batch_independent_results(client, auth, audio):
    response = client.post("/api/transcribe", headers=auth, files=[
        ("files", ("first.wav", audio)), ("files", ("bad.ogg", b"not audio")),
        ("files", ("last.wav", audio)),
    ])
    assert response.status_code == 200
    assert [r["status"] for r in response.json()["results"]] == ["done", "error", "done"]


def test_invalid_extension(client, auth, audio):
    row = upload(client, auth, audio, "script.exe").json()["results"][0]
    assert row["status"] == "error" and row["error"] == "Unsupported file extension."


def test_file_size(client, auth):
    row = upload(client, auth, b"x" * 8193).json()["results"][0]
    assert row["status"] == "error" and "size limit" in row["error"]


def test_duration(client, auth):
    # A compact compressed file avoids the 8 KB upload ceiling.
    import subprocess
    import imageio_ffmpeg
    encoded = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
                              "-t", "2", "-f", "ogg", "-c:a", "libopus", "pipe:1"], capture_output=True, check=True).stdout
    row = upload(client, auth, encoded, "long.ogg").json()["results"][0]
    assert row["status"] == "error" and "duration limit" in row["error"]


def test_request_size_streamed(client, auth, settings):
    # No Content-Length: raw ASGI body limit still applies.
    def chunks():
        yield b"a" * settings.max_body_bytes
        yield b"b"
    response = client.post("/api/transcribe", headers=auth, content=chunks())
    assert response.status_code == 413


def test_file_count_and_field_names(client, auth, audio):
    response = client.post("/api/transcribe", headers=auth, files=[("files", (f"{i}.wav", audio)) for i in range(4)])
    assert response.status_code == 400
    assert client.post("/api/transcribe", headers=auth, files={"wrong": ("a.wav", audio)}).status_code == 400
    assert client.post("/api/transcribe", headers=auth).status_code == 400


def test_engine_failure_does_not_lose_others(settings, auth, audio):
    class FailOnce(MockEngine):
        count = 0
        def transcribe(self, pcm):
            self.count += 1
            if self.count == 1:
                raise RuntimeError(TOKEN + " internal secret path")
            return super().transcribe(pcm)
    with TestClient(create_app(settings, FailOnce())) as client:
        response = client.post("/api/transcribe", headers=auth, files=[("files", ("a.wav", audio)), ("files", ("b.wav", audio))])
        assert [r["status"] for r in response.json()["results"]] == ["error", "done"]
        assert TOKEN not in response.text
        assert not list(settings.temp_dir.rglob("file-*"))
    assert list(settings.temp_dir.iterdir()) == [settings.temp_dir / ".server.lock"]


def test_session_login_logout_and_csrf(client, audio):
    assert client.post("/login", data={"token": "wrong"}).status_code == 401
    response = client.post("/login", data={"token": TOKEN}, follow_redirects=False)
    assert response.status_code == 303
    assert TOKEN not in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert client.get("/").status_code == 200
    assert upload(client, {"Origin": "http://evil.example"}, audio).status_code == 403
    assert upload(client, {}, audio).status_code == 403
    assert upload(client, {"Origin": "http://testserver"}, audio).status_code == 200
    assert client.post("/logout", headers={"Origin": "http://testserver"}, follow_redirects=False).status_code == 303
    assert client.get("/api/model").status_code == 401


def test_lan_form_login_preserves_origin(settings):
    origin = "http://192.0.2.10:8000"
    with TestClient(create_app(settings), base_url=origin) as client:
        response = client.get("/login")
        assert response.headers["referrer-policy"] == "same-origin"
        response = client.post("/login", data={"token": TOKEN},
                               headers={"Origin": origin}, follow_redirects=False)
        assert response.status_code == 303
        assert client.get("/").status_code == 200
        assert client.post("/logout", headers={"Origin": origin},
                           follow_redirects=False).status_code == 303


@pytest.mark.parametrize("origin", ["null", "http://evil.example"])
def test_login_still_refuses_untrusted_origins(client, origin):
    response = client.post("/login", data={"token": TOKEN}, headers={"Origin": origin})
    assert response.status_code == 403
    assert "localvox_session" not in client.cookies


def test_token_not_leaked(client, auth, audio, caplog):
    response = upload(client, auth, audio, TOKEN + ".wav")
    assert TOKEN not in response.text
    assert TOKEN not in caplog.text
    for route in ["/health", "/login", "/manifest.webmanifest", "/sw.js", "/", "/api/model"]:
        response = client.get(route, headers=auth)
        assert TOKEN not in response.text
        assert response.headers["cache-control"] == "no-store"


def test_safe_filename(client, auth, audio):
    row = upload(client, auth, audio, "../../etc/voice.wav").json()["results"][0]
    assert row["filename"] == "voice.wav" and row["status"] == "done"


def test_share_multipart_fallback(client, auth, audio):
    response = upload(client, auth, audio, route="/share")
    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "done"
    manifest = client.get("/manifest.webmanifest").json()
    assert manifest["share_target"]["enctype"] == "multipart/form-data"
    assert manifest["share_target"]["params"]["files"][0]["name"] == "files"
    assert client.get("/icon-192.png").content.startswith(b"\x89PNG")


def test_share_target_generic_audio_types(client, auth, audio):
    manifest = client.get("/manifest.webmanifest").json()
    accepted = manifest["share_target"]["params"]["files"][0]["accept"]
    assert {"audio/*", "application/ogg", "application/octet-stream", ".opus"} <= set(accepted)
    # Generic transport MIME does not bypass actual audio decoding.
    response = client.post("/share", headers=auth, files=[
        ("files", ("voice.opus", audio, "application/octet-stream")),
        ("files", ("invalid.opus", b"not audio", "application/octet-stream")),
    ])
    assert [row["status"] for row in response.json()["results"]] == ["done", "error"]
    assert 'rel="manifest"' in client.get("/login").text


def test_queue_is_bounded_and_model_serialized(settings, auth, audio):
    entered, release = threading.Event(), threading.Event()
    class Blocking(MockEngine):
        def transcribe(self, pcm):
            entered.set()
            assert release.wait(5)
            return super().transcribe(pcm)
    with TestClient(create_app(replace(settings, max_pending=1), Blocking())) as client:
        responses = []
        thread = threading.Thread(target=lambda: responses.append(upload(client, auth, audio)))
        thread.start()
        try:
            assert entered.wait(5)
            assert upload(client, auth, audio).status_code == 503
        finally:
            release.set()
            thread.join(5)
        assert responses[0].status_code == 200


def test_stale_audio_cleaned_on_start(settings):
    stale = settings.temp_dir / "localvox-abandoned"
    stale.mkdir(parents=True)
    (stale / "private-audio").write_bytes(b"private")
    with TestClient(create_app(settings)):
        assert not stale.exists()


def test_missing_model_is_honest(settings, auth, audio):
    with TestClient(create_app(replace(settings, backend="parakeet"))) as client:
        row = upload(client, auth, audio).json()["results"][0]
        assert row["status"] == "error"
        assert "download-model" in row["error"]


def test_configuration_rejects_missing_secret():
    with pytest.raises(ValueError):
        Settings(token="")


def test_playlist_content_is_rejected(client, auth):
    row = upload(client, auth, b"#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nfile:///etc/passwd\n", "fake.wav").json()["results"][0]
    assert row["status"] == "error"


def test_decode_timeout_cleans_files(monkeypatch, client, auth, audio, settings):
    from localvox import audio as module
    import subprocess
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("ffmpeg", 1)
    monkeypatch.setattr(module.subprocess, "run", timeout)
    row = upload(client, auth, audio).json()["results"][0]
    assert row["status"] == "error" and "timed out" in row["error"]
    assert not list(settings.temp_dir.rglob("file-*"))
