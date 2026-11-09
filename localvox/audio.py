from pathlib import Path
import shutil
import subprocess
import imageio_ffmpeg

EXTENSIONS = {".wav", ".flac", ".mp3", ".ogg", ".opus", ".m4a", ".mp4", ".aac", ".webm", ".amr", ".3gp"}


class AudioError(Exception):
    pass


def decode(source: Path, destination: Path, max_seconds: int, timeout: int) -> float:
    ffmpeg = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
    try:
        subprocess.run(
            [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-protocol_whitelist", "file,pipe",
             "-format_whitelist", "wav,flac,mp3,ogg,mov,matroska,webm,aac,amr",
             "-threads", "1", "-i", str(source.resolve()),
             "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-threads", "1",
             "-t", str(max_seconds + 1), "-f", "f32le", str(destination.resolve())],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=timeout, check=True,
        )
    except subprocess.TimeoutExpired:
        raise AudioError("Audio decoding timed out.") from None
    except (subprocess.CalledProcessError, OSError):
        raise AudioError("Cannot decode this file as audio. Export a supported audio file.") from None
    seconds = destination.stat().st_size / (16000 * 4)
    if seconds <= 0:
        raise AudioError("The file contains no decodable audio.")
    if seconds > max_seconds:
        raise AudioError(f"Audio exceeds the {max_seconds} second duration limit.")
    return seconds
