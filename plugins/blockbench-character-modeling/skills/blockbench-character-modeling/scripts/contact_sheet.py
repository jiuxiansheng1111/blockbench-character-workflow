"""Arrange genuine render files without recoloring, retouching, cropping or uploading."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", action="append", required=True, metavar="LABEL=PATH")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--cell", type=int, default=640, help="Fit whole view inside a square; nearest-neighbor resampling")
    parser.add_argument("--font", type=Path, help="Optional local font supporting your labels")
    args = parser.parse_args()
    provenance = args.output.with_suffix(args.output.suffix + ".json")
    if args.output.suffix.lower() != ".png":
        parser.error("Output must end in .png")
    if args.output.exists() or provenance.exists():
        parser.error("Output or provenance already exists; choose a new revision filename")
    if not (1 <= args.columns <= 8 and 64 <= args.cell <= 2048 and 1 <= len(args.image) <= 64):
        parser.error("Use 1..8 columns, 64..2048 cell pixels and 1..64 images")
    if math.ceil(len(args.image) / args.columns) * (args.cell + 44) * args.cell * args.columns > 80_000_000:
        parser.error("Contact sheet too large; reduce cell size")
    records, images = [], []
    for value in args.image:
        label, separator, filename = value.partition("=")
        if not separator:
            parser.error("Every --image must be LABEL=PATH")
        path = Path(filename)
        with Image.open(path) as raw:
            image = raw.convert("RGBA")
            original = list(image.size)
        image.thumbnail((args.cell, args.cell), Image.Resampling.NEAREST)
        images.append((label, image))
        records.append({"label": label, "file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "source_size": original, "placed_size": list(image.size)})
    canvas = Image.new("RGB", (args.columns * args.cell, math.ceil(len(images) / args.columns) * (args.cell + 44)), "#202329")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(str(args.font), 20) if args.font else ImageFont.load_default()
    for i, (label, image) in enumerate(images):
        x, y = (i % args.columns) * args.cell, (i // args.columns) * (args.cell + 44)
        draw.text((x + 12, y + 12), label, fill="white", font=font)
        canvas.paste(image, (x + (args.cell - image.width) // 2, y + 44 + (args.cell - image.height) // 2), image)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as output:
        canvas.save(output, format="PNG")
    with provenance.open("x", encoding="utf-8") as output:
        json.dump({"operation": "whole-view placement; nearest-neighbor scaling; labels outside view",
                   "inputs": records, "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}, output, indent=2, ensure_ascii=False)
    print(json.dumps({"output": str(args.output), "views": len(images), "provenance": str(provenance)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
