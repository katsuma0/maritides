#!/usr/bin/env python3
"""Draw the app icon: a wave crest on a blue rounded square.

Writes icon.svg plus the PNG sizes iOS and Android ask for. Rendered here in
pure Python (4x supersampled, then box-filtered) so the build needs no image
libraries.

Usage: python3 tools/make_icons.py
"""
from __future__ import annotations

import math
import struct
import zlib

BLUE = (0x2A, 0x78, 0xD6)      # series blue, matches --series
DEEP = (0x18, 0x4F, 0x95)      # blue 600, the water below the crest
FOAM = (0xFF, 0xFF, 0xFF)      # the crest line

SS = 4                          # supersampling factor
CORNER = 0.2237                 # corner radius as a fraction of the side


def wave_y(x: float) -> float:
    """Waterline height at normalised x, in normalised units from the top."""
    return 0.56 + 0.13 * math.sin((x - 0.12) * 2.0 * math.pi)


def sample(nx: float, ny: float) -> tuple[int, int, int, int]:
    """Colour a normalised point, or transparent outside the rounded square."""
    r = CORNER
    # Rounded-square test.
    cx = min(max(nx, r), 1.0 - r)
    cy = min(max(ny, r), 1.0 - r)
    if (nx - cx) ** 2 + (ny - cy) ** 2 > r * r:
        return (0, 0, 0, 0)

    surface = wave_y(nx)
    if ny < surface - 0.035:
        return BLUE + (255,)
    if ny < surface + 0.035:
        return FOAM + (255,)
    return DEEP + (255,)


def render(size: int) -> bytes:
    """Render `size`x`size` RGBA pixels, supersampled."""
    rows = []
    inv = 1.0 / (size * SS)
    for py in range(size):
        row = bytearray()
        for px in range(size):
            r = g = b = a = 0
            for sy in range(SS):
                ny = (py * SS + sy + 0.5) * inv
                for sx in range(SS):
                    nx = (px * SS + sx + 0.5) * inv
                    cr, cg, cb, ca = sample(nx, ny)
                    r += cr * ca
                    g += cg * ca
                    b += cb * ca
                    a += ca
            if a:
                row += bytes((round(r / a), round(g / a), round(b / a), round(a / (SS * SS))))
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))
    return b"".join(b"\0" + r for r in rows)


def write_png(path: str, size: int) -> None:
    raw = render(size)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    print(f"wrote {path} ({size}x{size})")


def write_svg(path: str) -> None:
    n = 64
    top = " ".join(
        f"{'L' if i else 'M'}{i * 512 / n:.1f} {wave_y(i / n) * 512:.1f}"
        for i in range(n + 1)
    )
    r = CORNER * 512
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="Tide">
  <defs><clipPath id="c"><rect width="512" height="512" rx="{r:.0f}" ry="{r:.0f}"/></clipPath></defs>
  <g clip-path="url(#c)">
    <rect width="512" height="512" fill="#{BLUE[0]:02x}{BLUE[1]:02x}{BLUE[2]:02x}"/>
    <path d="{top} L512 512 L0 512 Z" fill="#{DEEP[0]:02x}{DEEP[1]:02x}{DEEP[2]:02x}"/>
    <path d="{top}" fill="none" stroke="#ffffff" stroke-width="36"
          stroke-linecap="round" stroke-linejoin="round"/>
  </g>
</svg>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {path}")


if __name__ == "__main__":
    write_svg("icon.svg")
    write_png("apple-touch-icon.png", 180)
    write_png("icon-192.png", 192)
    write_png("icon-512.png", 512)
