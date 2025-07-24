#!/usr/bin/env python3
"""
Slice every tall PNG layer into 1000‑px‑high WebP tiles,
and launch a local web server to preview.

Usage
-----
$ python3 tile_images_and_serve.py            # in your project root
"""

import http.server, socketserver, pathlib, sys
from PIL import Image

# ─── settings ─────────────────────────────────────────────────────────────
TILE_H       = 1000          # px height of each slice
COMPRESSION  = 80            # WebP quality (0‑100, 80≈visually lossless)
LAYER_FILES = [
    "back.png", "layer3.png", "layer4.png", "layer5.png",
    "layer6.png", "layer7.png", "layer8.png", "layer9.png", "front.png", "ruler.png"
]
OUT_DIR      = pathlib.Path("tiles")
PORT         = 8000
# ─────────────────────────────────────────────────────────────────────────

def slice_img(path: pathlib.Path):
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    stem  = path.stem
    OUT_DIR.mkdir(exist_ok=True)

    n_tiles = (h + TILE_H - 1) // TILE_H
    for i in range(n_tiles):
        y0 = i * TILE_H
        y1 = min(y0 + TILE_H, h)
        tile = img.crop((0, y0, w, y1))
        tile.save(OUT_DIR / f"{stem}_{i}.webp", "WEBP", quality=COMPRESSION)

    print(f"✓ {stem}: {n_tiles} tiles")

def main():
    for f in LAYER_FILES:
        p = pathlib.Path(f)
        if not p.exists():
            sys.exit(f"✗ File not found: {p.resolve()}")
        slice_img(p)

    print(f"\nAll done! WebP tiles are in ./{OUT_DIR}")
    print(f"Now serving http://localhost:{PORT}/ (Ctrl‑C to quit)\n")

    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    main()

