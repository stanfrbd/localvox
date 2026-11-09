"""One persistent isolated worker; loads the model once, kills hung inference."""
from array import array
import multiprocessing as mp
from pathlib import Path
from typing import Protocol
import sys
from .models import CATALOG, verified


class Engine(Protocol):
    def transcribe(self, pcm: Path) -> str: ...
    def close(self) -> None: ...


class MockEngine:
    def transcribe(self, pcm: Path) -> str:
        return "[MOCK] Synthetic transcription; no speech model was run."

    def close(self):
        pass


def _worker(connection, model_path: str, threads: int):
    # Native output is not application logging. Suppress transcripts/filenames.
    import os
    with open(os.devnull, "w") as null:
        os.dup2(null.fileno(), 1)
        os.dup2(null.fileno(), 2)
    try:
        import transcribe_cpp
        with transcribe_cpp.Model(model_path, backend="cpu") as model:
            with model.session(n_threads=threads) as session:
                connection.send((True, "ready"))
                while True:
                    path = connection.recv()
                    if path is None:
                        break
                    try:
                        pcm = array("f")
                        with open(path, "rb") as source:
                            pcm.frombytes(source.read())
                        if sys.byteorder != "little":
                            pcm.byteswap()
                        connection.send((True, session.run(pcm, timestamps="none").text))
                    except Exception:
                        connection.send((False, "Transcription failed in the local engine."))
    except Exception:
        try:
            connection.send((False, "Could not load Parakeet Ultra. Check runtime and model cache."))
        except (BrokenPipeError, OSError):
            pass
    finally:
        connection.close()


class ParakeetEngine:
    def __init__(self, settings):
        self.settings = settings
        self.process = None
        self.connection = None

    def _receive(self):
        if not self.connection.poll(self.settings.task_timeout):
            self.close()
            raise RuntimeError("Local engine timed out; worker was stopped. Retry with shorter audio.")
        try:
            ok, value = self.connection.recv()
        except (EOFError, OSError):
            self.close()
            raise RuntimeError("Local engine stopped unexpectedly.") from None
        if not ok:
            raise RuntimeError(value)
        return value

    def transcribe(self, pcm: Path) -> str:
        if self.process is None or not self.process.is_alive():
            self.close()
            model = self.settings.model_dir / CATALOG["filename"]
            if not verified(model):
                raise RuntimeError("Parakeet Ultra is missing or invalid. Run localvox download-model.")
            context = mp.get_context("spawn")
            self.connection, child = context.Pipe()
            self.process = context.Process(target=_worker, args=(child, str(model.resolve()), self.settings.cpu_threads))
            self.process.start()
            child.close()
            try:
                self._receive()
            except Exception:
                self.close()
                raise
        self.connection.send(str(pcm.resolve()))
        return self._receive()

    def close(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=5)
            if self.process.is_alive():
                self.process.kill()
                self.process.join()
            self.process.close()
            self.process = None
        if self.connection is not None:
            self.connection.close()
            self.connection = None
