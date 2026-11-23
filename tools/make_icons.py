"""Render the launcher icon at the Sailfish sizes (standard library only; development only).

    python3 tools/make_icons.py
"""
import math
import os
import struct
import zlib

SIZES = (86, 108, 128, 172)
SAMPLES = 4                                  # 4 x 4 samples per pixel for smooth edges
TOP, BOTTOM = (0x2E, 0xC4, 0xB6), (0x1B, 0x5E, 0xA8)
CORNER = 0.225                               # corner radius of the rounded square
OX, OY = 0.244, 0.756                        # the feed symbol's corner (bottom left)
DOT = 0.068
WAVES = ((0.156, 0.264), (0.361, 0.469))     # inner and outer radius of the two waves


def sample(x, y):
    """(r, g, b, a) at a point of the unit square."""
    cx = min(max(x, CORNER), 1 - CORNER)
    cy = min(max(y, CORNER), 1 - CORNER)
    if math.hypot(x - cx, y - cy) > CORNER:
        return 0, 0, 0, 0
    far = math.hypot(x - OX, y - OY)
    wave = x >= OX and y <= OY and any(lo <= far <= hi for lo, hi in WAVES)
    if far <= DOT or wave:
        return 255, 255, 255, 255
    t = x * 0.35 + y * 0.65
    return tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)) + (255,)


def render(size):
    rows = []
    n = SAMPLES * SAMPLES
    for py in range(size):
        row = bytearray([0])                 # PNG filter type "none"
        for px in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    r, g, b, a = sample((px + (sx + 0.5) / SAMPLES) / size,
                                        (py + (sy + 0.5) / SAMPLES) / size)
                    acc[0] += r * a
                    acc[1] += g * a
                    acc[2] += b * a
                    acc[3] += a
            alpha = acc[3]
            row += bytes((acc[0] // alpha, acc[1] // alpha, acc[2] // alpha, alpha // n)
                         if alpha else (0, 0, 0, 0))
        rows.append(bytes(row))
    return b"".join(rows)


def chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def png(size):
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(render(size), 9))
            + chunk(b"IEND", b""))


if __name__ == "__main__":
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "icons")
    for s in SIZES:
        folder = os.path.join(root, "%dx%d" % (s, s))
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "harbour-feedpond.png"), "wb") as handle:
            handle.write(png(s))
        print("wrote %dx%d" % (s, s))
