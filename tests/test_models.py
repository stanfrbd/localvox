from dataclasses import replace
import hashlib
import io
from pathlib import Path
import pytest
from localvox import models
from localvox.engine import ParakeetEngine


def test_atomic_model_download_and_cache(monkeypatch, tmp_path):
    data = b"synthetic fake model for downloader test"
    monkeypatch.setitem(models.CATALOG, "size", len(data))
    monkeypatch.setitem(models.CATALOG, "sha256", hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(models.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(data))
    target = models.download(tmp_path)
    assert models.verified(target)
    monkeypatch.setattr(models.urllib.request, "urlopen", lambda *a, **kw: pytest.fail("cache should be reused"))
    assert models.download(tmp_path) == target
    assert not list(tmp_path.glob("*.part"))


def test_download_integrity_failure_cleans_partial(monkeypatch, tmp_path):
    monkeypatch.setitem(models.CATALOG, "size", 4)
    monkeypatch.setitem(models.CATALOG, "sha256", "wrong")
    monkeypatch.setattr(models.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(b"fake"))
    with pytest.raises(RuntimeError, match="SHA-256"):
        models.download(tmp_path)
    assert not list(tmp_path.glob("*.part"))
    assert not (tmp_path / models.CATALOG["filename"]).exists()


def test_worker_timeout_stops_worker_before_return(settings):
    class Connection:
        closed = False
        def poll(self, timeout): return False
        def close(self): self.closed = True
    class Process:
        alive = True
        stopped = False
        def is_alive(self): return self.alive
        def terminate(self): self.alive = False; self.stopped = True
        def join(self, timeout=None): pass
        def close(self): pass
    engine = ParakeetEngine(settings)
    connection, process = Connection(), Process()
    engine.connection, engine.process = connection, process
    with pytest.raises(RuntimeError, match="timed out"):
        engine._receive()
    assert process.stopped and connection.closed
    assert engine.process is None
