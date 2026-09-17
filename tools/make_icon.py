"""Regenerate the app icon files from the AIFarm logo.

    python tools/make_icon.py [--source "/path/to/AIFarm_Logo _cropped.png"]

Writes src/wl20_exporter/assets/icon.{png,ico,icns}: the logo's yellow-framed
square trimmed to its own frame and centred on a square canvas, so the mark
stays even at 512/256/128/64/48/32/24/16 px.

The default source is the office logo file on this machine.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

DEFAULT_SOURCE = Path(
    "/home/visionai/Desktop/deepstream-facego-tensorrt/static/src/AIFarm_Logo _cropped.png")
OUT_DIR = Path(__file__).resolve().parents[1] / "src" / "wl20_exporter" / "assets"
YELLOW = (249, 239, 36, 255)  # sampled from the logo's frame


def is_yellow(pixel) -> bool:
    red, green, blue, alpha = pixel
    return alpha > 40 and red > 200 and green > 190 and blue < 140


def build(source: Path, out_dir: Path = OUT_DIR) -> list:
    out_dir.mkdir(parents=True, exist_ok=True)
    image = Image.open(source).convert("RGBA")
    width, height = image.size
    pixels = image.load()

    min_x, min_y, max_x, max_y = width, height, -1, -1
    for y in range(height):
        for x in range(width):
            if not is_yellow(pixels[x, y]):
                min_x, min_y = min(min_x, x), min(min_y, y)
                max_x, max_y = max(max_x, x), max(max_y, y)
    if max_x < 0:
        raise SystemExit("no non-yellow content found in the source image")

    pad = min(min_x, min_y, width - 1 - max_x, height - 1 - max_y)
    content = image.crop((min_x, min_y, max_x + 1, max_y + 1))
    side = max(content.width, content.height) + 2 * pad
    canvas = Image.new("RGBA", (side, side), YELLOW)
    canvas.paste(content, ((side - content.width) // 2, (side - content.height) // 2), content)
    print(f"source {width}x{height} -> content {content.width}x{content.height} "
          f"| frame {pad}px | square {side}x{side}")

    master = canvas.resize((512, 512), Image.LANCZOS)
    written = []
    png_path = out_dir / "icon.png"
    master.save(png_path, optimize=True)
    written.append(png_path)

    ico_path = out_dir / "icon.ico"
    master.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                 (128, 128), (256, 256)])
    written.append(ico_path)

    icns_path = out_dir / "icon.icns"
    master.save(icns_path)
    written.append(icns_path)

    for path in written:
        print(f"wrote {path} ({path.stat().st_size} bytes)")
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    if not args.source.is_file():
        print(f"source logo not found: {args.source}", file=sys.stderr)
        return 2
    build(args.source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
