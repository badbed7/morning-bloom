"""Generate transparent PNG and multi-size Windows ICO from the in-game daisy."""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def generate_icons(directory):
    from PySide6.QtCore import QBuffer, QIODevice
    sys.path.insert(0, str(ROOT / 'python'))
    from morning_bloom.app_icon import daisy_image

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if not daisy_image(120).save(str(directory / 'morning-bloom-120.png')):
        raise RuntimeError('Could not save the daisy PNG')
    sizes = (16, 24, 32, 48, 64, 128, 256)
    entries, images = [], []
    offset = 6 + 16 * len(sizes)
    for size in sizes:
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        if not daisy_image(size).save(buffer, 'PNG'):
            raise RuntimeError('Could not encode the daisy icon')
        data = bytes(buffer.data())
        entries.append(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        images.append(data)
        offset += len(data)
    path = directory / 'morning-bloom.ico'
    path.write_bytes(struct.pack('<HHH', 0, 1, len(sizes)) + b''.join(entries + images))
    return path


if __name__ == '__main__':
    print(generate_icons(ROOT / 'assets/icons'))
