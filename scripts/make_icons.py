"""Generate original, geometric PNG icons with only the standard library."""
from pathlib import Path
import struct
import zlib


def chunk(kind, data):
    return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))


for size in (192, 512):
    pixels = bytearray()
    for y in range(size):
        pixels.append(0)
        for x in range(size):
            # Three simple waveform bars.
            bar = any(abs(x / size - center) < .045 and abs(y / size - .5) < height
                      for center, height in ((.32, .15), (.5, .28), (.68, .2)))
            pixels.extend((247, 247, 239) if bar else (24, 59, 50))
    data = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', size, size, 8, 2, 0, 0, 0))
    data += chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')
    Path(f'localvox/static/icon-{size}.png').write_bytes(data)
